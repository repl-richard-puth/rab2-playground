import json
import logging
import time
import boto3
import requests
import re
import csv

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

def get_jira_credentials():
    email = ssm.get_parameter(Name='/cd/jira/rap20-email', WithDecryption=True)['Parameter']['Value']
    token = ssm.get_parameter(Name='/cd/jira/rap20-token', WithDecryption=True)['Parameter']['Value']
    domain = ssm.get_parameter(Name='/cd/jira/domain')['Parameter']['Value']
    return email, token, domain

def fetch_jira_ticket(jira_key):
    email, token, domain = get_jira_credentials()
    url = f"https://{domain}/rest/api/3/issue/{jira_key}"

    headers = {
        "Accept": "application/json"
    }

    auth = (email, token)
    response = requests.get(url, headers=headers, auth=auth)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch JIRA ticket {jira_key}: {response.text}")

    data = response.json()
    summary = data['fields']['summary']
    description = data['fields']['description']['content'][0]['content'][0]['text'] \
        if data['fields'].get('description') else "No description found"

    return {
        "key": jira_key,
        "summary": summary,
        "description": description
    }

def extract_jira_key(text):
    # Example: look for patterns like [anything]-[numbers]
    match = re.search(r'\b[\w]+-\d+\b', text, re.IGNORECASE)
    return match.group(0).upper() if match else None

def load_prompt_templates_from_s3(bucket="rab20-prompts", key="Risk Assessment Bot Prompts.csv "):
    prompt_map = {}
    try:
        s3 = boto3.client('s3')
        response = s3.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read().decode('utf-8-sig').splitlines()

        reader = csv.DictReader(content)
        for row in header:
            repo = row['Repo'].strip()
            prompt = row['Prompt'].strip()
            prompt_map[repo] = prompt

        return prompt_map
    except Exception as e:
        logger.warning(f"⚠️ Failed to load prompt templates from S3: {e}")
        return {}

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

        # Try to extract JIRA key from PR title
        jira_key = extract_jira_key(pr_title)
        # Fetch JIRA information
        if jira_key:
            logger.info(f"🔎 Found JIRA key in PR title: {jira_key}")
            try:
                jira_data = fetch_jira_ticket(jira_key)
                logger.info(f"📄 JIRA Summary: {jira_data['summary']}")
                logger.info(f"📃 JIRA Description: {jira_data['description'][:500]}")  # trim long desc
            except Exception as je:
                logger.warning(f"⚠️ Could not retrieve JIRA ticket: {str(je)}")
        else:
            logger.info("❌ No JIRA key found in PR title.")

        prompt_templates = load_prompt_templates_from_s3()
        repo_name = body.get('repository', {}).get("name","")
        repo_prompt = prompt_templates.get(repo_name, "Default Risk Assessment Prompt")
        logger.info(f"✍️ Loaded Prompt for {repo_name}: {repo_prompt}")

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

