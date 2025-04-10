import csv

def load_prompt_templates_from_file(file_path="Risk Assessment Bot Prompts.csv"):
    prompt_map = {}
    try:
        with open(file_path, mode='r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            headers = reader.fieldnames
            print(f"🧾 CSV Headers Found: {headers}")
            
            if not headers or 'Repo' not in headers or 'Prompt' not in headers:
                raise ValueError("CSV must have 'Repo' and 'Prompt' columns.")
            
            for row in reader:
                print(f"📦 Row: {row}")
                repo = row['Repo'].strip()
                prompt = row['Prompt'].strip()
                prompt_map[repo] = prompt
        return prompt_map
    except Exception as e:
        print(f"⚠️ Failed to load prompt templates: {e}")
        return {}

# Run the test
if __name__ == "__main__":
    templates = load_prompt_templates_from_file("Risk Assessment Bot Prompts.csv")
    for repo, prompt in templates.items():
        print(f"[{repo}] -> {prompt}")
