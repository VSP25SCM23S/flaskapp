'''
Goal of Flask Microservice:
1. Flask will take the repository_name such as angular, angular-cli, material-design, D3 from the body of the api sent from React app and 
   will utilize the GitHub API to fetch the created and closed issues. Additionally, it will also fetch the author_name and other 
   information for the created and closed issues.
2. It will use group_by to group the data (created and closed issues) by month and will return the grouped data to client (i.e. React app).
3. It will then use the data obtained from the GitHub API (i.e Repository information from GitHub) and pass it as a input request in the 
   POST body to LSTM microservice to predict and forecast the data.
4. The response obtained from LSTM microservice is also return back to client (i.e. React app).

Use Python/GitHub API to retrieve Issues/Repos information of the past 1 year for the following repositories:
- https: // github.com/angular/angular
- https: // github.com/angular/material
- https: // github.com/angular/angular-cli
- https: // github.com/d3/d3
'''
# Import all the required packages 
import os
from flask import Flask, jsonify, request, make_response, Response
from flask_cors import CORS
import json
import dateutil.relativedelta
from dateutil import *
from datetime import date
import pandas as pd
import requests

from dotenv import load_dotenv

load_dotenv()

# Initilize flask app
app = Flask(__name__)
# Handles CORS (cross-origin resource sharing)
CORS(app)

# Add response headers to accept all types of  requests
def build_preflight_response():
    response = make_response()
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    response.headers.add("Access-Control-Allow-Methods",
                         "PUT, GET, POST, DELETE, OPTIONS")
    return response

# Modify response headers when returning to the origin
def build_actual_response(response):
    response.headers.set("Access-Control-Allow-Origin", "*")
    response.headers.set("Access-Control-Allow-Methods",
                         "PUT, GET, POST, DELETE, OPTIONS")
    return response

'''
API route path is  "/api/forecast"
This API will accept only POST request
'''
@app.route('/api/github', methods=['POST'])
def github():
    try:
        body = request.get_json(force=True)
        if not body or 'repository' not in body:
            return jsonify({"error": "Missing 'repository' in request body"}), 400

        repo_name = body['repository']
        token = os.environ.get('GITHUB_TOKEN', None)
        if not token or token == 'YOUR_GITHUB_TOKEN':
            return jsonify({"error": "GitHub token not found or invalid"}), 500

        headers = {"Authorization": f'token {token}'}
        GITHUB_URL = "https://api.github.com/"
        repository_url = f"{GITHUB_URL}repos/{repo_name}"

        try:
            repository = requests.get(repository_url, headers=headers)
            repository.raise_for_status()
            repository = repository.json()
        except requests.RequestException as e:
            return jsonify({"error": f"GitHub repo fetch failed: {str(e)}"}), 502

        today = date.today()
        issues_response = []

        for i in range(12):
            last_month = today + dateutil.relativedelta.relativedelta(months=-1)
            search_query = f"type:issue repo:{repo_name} created:{last_month}..{today}"
            query_url = f"{GITHUB_URL}search/issues?q={search_query}&per_page=10"
            try:
                search_issues = requests.get(query_url, headers=headers).json()
                issues_items = search_issues.get("items", [])
            except Exception as e:
                return jsonify({"error": f"Failed to fetch issues: {str(e)}"}), 502

            for issue in issues_items:
                try:
                    issues_response.append({
                        "issue_number": issue["number"],
                        "created_at": issue["created_at"][:10] if issue.get("created_at") else None,
                        "closed_at": issue["closed_at"][:10] if issue.get("closed_at") else None,
                        "labels": [label["name"] for label in issue.get("labels", [])],
                        "State": issue["state"],
                        "Author": issue["user"]["login"]
                    })
                except KeyError:
                    continue  # skip malformed entries

            today = last_month

        if not issues_response:
            return jsonify({"error": "No issues found for the repo"}), 404

        df = pd.DataFrame(issues_response)
        if 'created_at' not in df.columns or 'closed_at' not in df.columns:
            return jsonify({"error": "Missing created/closed dates in issue data"}), 500

        # Grouping & Forecast Preparation
        df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
        df['closed_at'] = pd.to_datetime(df['closed_at'], errors='coerce')

        created_monthly = df['created_at'].dt.to_period("M").value_counts().sort_index()
        closed_monthly = df['closed_at'].dt.to_period("M").value_counts().sort_index()

        created = [[str(month), count] for month, count in created_monthly.items()]
        closed = [[str(month), count] for month, count in closed_monthly.items()]

        # Call LSTM Forecast Service
        LSTM_API_URL = "https://lstm-final-443901594551.us-central1.run.app/api/forecast"
        try:
            created_at_response = requests.post(LSTM_API_URL, json={
                "issues": issues_response, "type": "created_at", "repo": repo_name.split("/")[1]
            })
            closed_at_response = requests.post(LSTM_API_URL, json={
                "issues": issues_response, "type": "closed_at", "repo": repo_name.split("/")[1]
            })
            created_at_images = created_at_response.json()
            closed_at_images = closed_at_response.json()
        except Exception as e:
            return jsonify({"error": f"LSTM service failed: {str(e)}"}), 502

        return jsonify({
            "created": created,
            "closed": closed,
            "starCount": repository.get("stargazers_count", 0),
            "forkCount": repository.get("forks_count", 0),
            "createdAtImageUrls": created_at_images,
            "closedAtImageUrls": closed_at_images
        })

    except Exception as e:
        return jsonify({"error": f"Unexpected server error: {str(e)}"}), 500
    
@app.route('/api/github/details', methods=['POST'])
def github_details():
    body = request.get_json()
    token = os.environ.get('GITHUB_TOKEN', 'YOUR_GITHUB_TOKEN')
    headers = {
        "Authorization": f'token {token}'
    }
    GITHUB_URL = "https://api.github.com/"
    response_list = []

    for repo in body:
        repo_name = repo['name']
        repository_url = GITHUB_URL + "repos/" + repo_name
        issues_url = GITHUB_URL + f"search/issues?q=repo:{repo_name}+type:issue"
        closed_issues_url = GITHUB_URL + f"search/issues?q=repo:{repo_name}+type:issue+state:closed"

        try:
            repo_data = requests.get(repository_url, headers=headers).json()
            issues_data = requests.get(issues_url, headers=headers).json()
            closed_issues_data = requests.get(closed_issues_url, headers=headers).json()

            repo_response = {
                "name": repo_name,
                "stars": repo_data.get("stargazers_count", 0),
                "forks": repo_data.get("forks_count", 0),
                "total_issues": issues_data.get("total_count", 0),
                "closed_issues": closed_issues_data.get("total_count", 0),
            }

            response_list.append(repo_response)

        except Exception as e:
            print(f"Error processing repo {repo_name}: {e}")

    return jsonify(response_list)



# Run flask app server on port 5000
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
