# Role & Workflow Definition
You are now a Senior Full-Stack Engineer responsible for developing an external monitoring and analytics service for a self-hosted Navidrome music server.
Throughout the upcoming development process, you MUST strictly adhere to the following single-step iterative workflow. You are absolutely forbidden to proceed to the next stage without my explicit confirmation:
[Current Stage Requirement] -> [Write Code] -> [Provide Testing Plan] -> [I Feedback Test Results/Errors] -> [Resolve Issues & Fix] -> [Test Passed] -> [Next Stage Requirement]

# Project Background & Core Tech Stack Constraints
- **Target**: An independent monitoring dashboard outside of Navidrome that reads Navidrome data to track the usage of various frontend players, user listening habits, and server transcoding loads.
- **Data Source**: Fetch real-time data by polling the Navidrome-compatible Subsonic API (specifically the `getNowPlaying` endpoint).
- **Authentication**: Utilize the standard Subsonic API Token authentication (password + salt MD5 hash). A pre-configured Navidrome Admin account will be used strictly for read-only data pulling.
- **Data Persistence**: SQLite MUST be implemented to record snapshots of the playback status during each pull. This will be used for multi-dimensional historical data aggregation and analysis.
- **Deployment Environment**: The final deliverable must be containerized with a `docker-compose.yml`. This service will be deployed on the same host within the same Docker network as Navidrome (expected to communicate directly via an internal network address like `http://navidrome:4533`).
- **Privacy & Code Standards**: Properly configure `.gitignore`. It is strictly forbidden to hardcode accounts, passwords, tokens, internal IPs, or `.db` database files into the source code or commit them to Git. All secrets must be managed via environment variables (`.env`).

# Staged Development Breakdown

## Stage 1: Basic Probe & Subsonic API Connection
- **Requirement**: Set up the basic project skeleton and implement secure authentication and API requests. The service must read the Navidrome URL, username, and password from the `.env` file. Generate the authentication token according to the Subsonic API protocol, successfully request the `getNowPlaying` endpoint, and print the raw JSON/XML playback data to the console.
- **Acceptance Criteria**: The request is successfully sent without errors, and the parsed playback metadata (including client name, bitrate, track info, etc.) is visible in the console.

## Stage 2: SQLite Database Integration & Data Cleansing
- **Requirement**: Design a reasonable SQLite database schema. The service needs to poll the API at a fixed interval (e.g., every 10 seconds). Persist the instantaneous playback status into SQLite as historical slices or playback logs, ensuring that duplicate playback session records are filtered out.
- **Acceptance Criteria**: The database file is successfully generated. After multiple polling cycles, the database accurately records continuous playback history and can distinguish data sources by client names (e.g., Feishin, Strawberry).

## Stage 3: Statistical Aggregation Logic & Internal APIs
- **Requirement**: Write data analysis logic based on the historical data in SQLite. Generate statistical results across several core dimensions: e.g., "usage duration/frequency ratio of different frontend players," "user playback statistics," and "frequency and bitrate status of audio transcoding." Wrap these statistical results into internal API endpoints for the frontend to call.
- **Acceptance Criteria**: The statistical data for the above dimensions can be retrieved in JSON format via simple HTTP GET requests, and the data logic is accurate.

## Stage 4: Visual Data Dashboard
- **Requirement**: Develop a minimalist web frontend (you may use a lightweight, off-the-shelf charting library). The page will call the endpoints from Stage 3 and display the statistics using intuitive charts (pie charts, bar charts, or data tables).
- **Acceptance Criteria**: Accessing the service port via a browser clearly displays the charts for each data metric, with no obvious UI misalignment or console errors.

## Stage 5: Docker Containerization & Delivery Cleanup
- **Requirement**: Write the `Dockerfile` and `docker-compose.yml`. Organize the volume mount structure (ensuring the SQLite database and config files are mounted externally), finalize the `.gitignore`, and clean up any dirty data or redundant code from the testing phases.
- **Acceptance Criteria**: The service can be started with a single `docker compose up -d` command. The dashboard functions normally after startup, and historical statistical data is not lost when the container is destroyed and rebuilt.
