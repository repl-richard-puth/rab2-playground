import json
import logging
import time
import boto3
import requests

# Setup structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

ssm = boto3.client("ssm")

def get_github_token():
    response = ssm.get_parameter(Name="/cd/github-token/rap20-pr-token", WithDecryption=True)
    return response["Parameter"]["Value"]

def fetch_pr_diff(diff_url):
    token = get_github_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3.diff"
    }

    logger.info(f"🌐 Fetching PR diff from: {diff_url}")
    response = requests.get(diff_url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"GitHub API returned {response.status_code}: {response.text}")

    logger.info(f"✅ PR diff fetched successfully. Size: {len(response.text)} characters")
    return response.text

def lambda_handler(event, context):
    start_time = time.time()  # Start execution timer
    request_id = context.aws_request_id if context else "UNKNOWN"

    logger.info(f"🔹 Lambda Invoked | Request ID: {request_id}")

    try:
        # Pretty-print the event payload for readability
        formatted_event = json.dumps(event, indent=2)
        logger.info(f"📥 Received Event:\n{formatted_event}")

        # API Gateway sends the event body as a string; parse it if needed
        body = json.loads(event["body"]) if "body" in event else event

        # Validate it's a PR event
        if body.get("action") != "opened":
            logger.info("⚠️ Event is not a new PR opening. Ignoring.")
            return {"statusCode": 200, "body": json.dumps({"message": "Not a new PR event"})}

        pr_data = body.get("pull_request", {})
        if not pr_data or pr_data.get("draft", False):
            logger.info("🚫 PR is a draft. Ignoring.")
            return {"statusCode": 200, "body": json.dumps({"message": "Ignoring draft PR"})}

        # Log PR details
        pr_title = pr_data.get("title", "Unknown PR")
        pr_number = pr_data.get("number", "Unknown")
        repo_name = body.get("repository", {}).get("full_name", "Unknown Repo")
        diff_url = pr_data.get("diff_url")

        logger.info(f"✅ Processing PR: #{pr_number} | Title: {pr_title} | Repo: {repo_name}")

        # Fetch the diff from Github
        diff = fetch_pr_diff(diff_url)

        # Strictly for testing purposes. Once everything is ready, we will pass the diff into the prompt.
        snippet = diff[:1000] + ('...' if len (diff) > 1000 else '')
        logger.info(f"📝 Diff snippet: {snippet}")

        execution_time = time.time() - start_time
        logger.info(f"⏱ Execution Time: {execution_time:.3f} seconds")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "PR event processed successfully",
                "pr_number": pr_number,
                "diff_length": len(diff)
            })
        }

    except Exception as e:
        logger.error(f"❌ Error Processing Webhook: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

