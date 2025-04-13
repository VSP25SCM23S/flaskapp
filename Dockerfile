# Use official slim Python image
FROM python:3.10-slim

# Set environment variables
ENV PORT=8080
ENV HOSTDIR=0.0.0.0

# Set working directory
WORKDIR /app

# Copy dependencies first (for Docker layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Expose the port Flask will use (Cloud Run uses 8080)
EXPOSE 8080

# Command to run the application
CMD ["python", "app.py"]
