import os
import subprocess
import shutil
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()
API_KEY = os.getenv("API_KEY")

# Initialize Flask and OpenAI client
app = Flask(__name__)
client = OpenAI(api_key=API_KEY)

# Define a temporary file path for execution
GENERATED_FILE = 'generated_code.py'
GITHUB_PAGES_DIR = 'docs'  # GitHub Pages can serve from /docs folder


def generate_code_from_llm(prompt):
    """
    Generate code using OpenAI's API based on the user's prompt.
    """
    try:
        # Use a model appropriate for code generation, like gpt-4o or gpt-3.5-turbo
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert Python programmer. Write only the runnable Python code requested by the user. Do not include any explanations, markdown formatting (like ```python), or extra text—just the raw code. The code should be self-contained."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        # Extract the text content
        content = completion.choices[0].message.content
        return content.strip() if content else "Error: No content returned from API"
    except Exception as e:
        return f"Error: Could not connect to OpenAI API. {e}"


# Route for the main page
@app.route('/')
def index():
    return render_template('index.html')


# Route for generating code
@app.route('/generate_code', methods=['POST'])
def generate_code():
    data = request.json
    prompt = data.get('prompt', '') if data else ''

    if not prompt:
        return jsonify({"code": "", "message": "Please enter a prompt."})

    generated_code = generate_code_from_llm(prompt)
    
    # Check if the response is an error message
    if generated_code.startswith("Error:"):
        return jsonify({"code": generated_code, "message": "API Error"})

    return jsonify({
        "code": generated_code,
        "message": "Code generated successfully."
    })


# Route for 'deploying' (executing) the generated code
@app.route('/deploy_code', methods=['POST'])
def deploy_code():
    data = request.json
    code = data.get('code', '') if data else ''

    if not code:
        return jsonify({"output": "Error: No code provided for execution."})

    # 1. Save the code to a temporary file
    try:
        with open(GENERATED_FILE, 'w') as f:
            f.write(code)
    except Exception as e:
        return jsonify({"output": f"Error saving file: {e}"})

    # 2. Execute the file using subprocess
    try:
        # Run the Python file, setting a timeout to prevent infinite loops
        result = subprocess.run(
            ['python', GENERATED_FILE],  # Use 'python' for Windows
            capture_output=True,
            text=True,
            timeout=10,
            check=True  # Raise error on non-zero exit code
        )
        output = f"Execution Successful:\n\n{result.stdout}"
    
    except subprocess.CalledProcessError as e:
        output = f"Execution Failed (Runtime Error):\n\n{e.stderr}"
    except subprocess.TimeoutExpired:
        output = "Execution Failed (Timeout): The code took too long to run."
    except FileNotFoundError:
        output = "Execution Failed: Python interpreter not found."
    except Exception as e:
        output = f"An unexpected error occurred during execution: {e}"
    
    # Clean up the generated file (optional, but good practice)
    # os.remove(GENERATED_FILE)

    return jsonify({"output": output})


# Route for deploying to GitHub Pages
@app.route('/deploy_to_github', methods=['POST'])
def deploy_to_github():
    data = request.json
    code = data.get('code', '') if data else ''
    auto_push = data.get('auto_push', True) if data else True
    
    if not code:
        return jsonify({"status": "error", "message": "No code provided for deployment."})
    
    deployment_log = []
    
    try:
        # Create docs directory if it doesn't exist
        docs_dir = Path(GITHUB_PAGES_DIR)
        docs_dir.mkdir(exist_ok=True)
        deployment_log.append("✅ Created /docs directory")
        
        # Save the Python code
        code_file = docs_dir / 'generated_code.py'
        with open(code_file, 'w') as f:
            f.write(code)
        deployment_log.append("✅ Saved Python code")
        
        # Execute the code and capture output
        result = subprocess.run(
            ['python', str(code_file)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
        
        output = result.stdout if result.stdout else result.stderr
        
        # Check if output looks like HTML
        if '<html' in output.lower() or '<!doctype' in output.lower():
            # Save as index.html directly
            index_file = docs_dir / 'index.html'
            with open(index_file, 'w', encoding='utf-8') as f:
                f.write(output)
            deployment_log.append("✅ Generated HTML page")
        else:
            # Wrap plain text/code output in HTML
            html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generated Output</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-white min-h-screen p-8">
    <div class="max-w-4xl mx-auto">
        <h1 class="text-4xl font-bold mb-6 text-blue-400">Generated Output</h1>
        <div class="bg-gray-800 rounded-lg p-6 shadow-xl">
            <pre class="whitespace-pre-wrap font-mono text-green-400">{output}</pre>
        </div>
        <footer class="mt-8 text-center text-gray-400">
            <p>Generated by LLM Code Deployment Tool</p>
        </footer>
    </div>
</body>
</html>"""
            
            index_file = docs_dir / 'index.html'
            with open(index_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            deployment_log.append("✅ Created HTML wrapper")
        
        # Create a README for GitHub Pages
        readme_file = docs_dir / 'README.md'
        with open(readme_file, 'w') as f:
            f.write(f"""# Generated Code Output

This page was automatically generated and deployed by the LLM Code Deployment Tool.

## Auto-Deployment

This project uses automated GitHub Pages deployment.

## Source Code

The Python code that generated this output is available in `generated_code.py`.
""")
        deployment_log.append("✅ Created README.md")
        
        # Automated Git Operations
        if auto_push:
            deployment_log.append("\n🔄 Starting automated Git deployment...")
            
            # Check if git is initialized
            git_check = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            
            if git_check.returncode != 0:
                # Initialize git if not already done
                subprocess.run(['git', 'init'], check=True, cwd=os.getcwd())
                deployment_log.append("✅ Initialized Git repository")
                
                # Check for remote
                remote_check = subprocess.run(
                    ['git', 'remote', 'get-url', 'origin'],
                    capture_output=True,
                    text=True,
                    cwd=os.getcwd()
                )
                
                if remote_check.returncode != 0:
                    return jsonify({
                        "status": "partial",
                        "message": "Files created but Git remote not configured",
                        "log": deployment_log,
                        "instructions": """
⚠️ Git remote not configured!

Please run these commands:
1. git remote add origin https://github.com/[username]/[repo-name].git
2. Then try deploying again for automatic push
"""
                    })
            
            # Add files to git
            add_result = subprocess.run(
                ['git', 'add', 'docs/'],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            deployment_log.append("✅ Added files to Git")
            
            # Commit changes
            commit_result = subprocess.run(
                ['git', 'commit', '-m', 'Auto-deploy: Generated code to GitHub Pages'],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            
            if commit_result.returncode == 0:
                deployment_log.append("✅ Committed changes")
            else:
                # Check if there are no changes to commit
                if "nothing to commit" in commit_result.stdout.lower():
                    deployment_log.append("ℹ️ No changes to commit")
                else:
                    deployment_log.append(f"⚠️ Commit warning: {commit_result.stderr}")
            
            # Push to GitHub
            push_result = subprocess.run(
                ['git', 'push', 'origin', 'main'],
                capture_output=True,
                text=True,
                cwd=os.getcwd(),
                timeout=30
            )
            
            if push_result.returncode == 0:
                deployment_log.append("✅ Pushed to GitHub successfully!")
                deployment_log.append("\n🎉 DEPLOYMENT COMPLETE!")
                
                # Get remote URL to provide the Pages URL
                remote_result = subprocess.run(
                    ['git', 'remote', 'get-url', 'origin'],
                    capture_output=True,
                    text=True,
                    cwd=os.getcwd()
                )
                
                if remote_result.returncode == 0:
                    remote_url = remote_result.stdout.strip()
                    # Extract username and repo from URL
                    if 'github.com' in remote_url:
                        parts = remote_url.replace('.git', '').split('/')
                        if len(parts) >= 2:
                            username = parts[-2].split(':')[-1]
                            repo = parts[-1]
                            pages_url = f"https://{username}.github.io/{repo}/"
                            deployment_log.append(f"\n🌐 Your site will be live at:\n   {pages_url}")
                            deployment_log.append("\n⚠️ Note: First deployment may take 1-2 minutes")
                            deployment_log.append("⚠️ Make sure GitHub Pages is enabled in repo settings!")
                
                return jsonify({
                    "status": "success",
                    "message": "Automatically deployed to GitHub Pages!",
                    "log": deployment_log
                })
            else:
                # Push failed - provide helpful error
                error_msg = push_result.stderr
                deployment_log.append(f"❌ Push failed: {error_msg}")
                
                if "rejected" in error_msg.lower():
                    deployment_log.append("\n💡 Tip: Try running 'git pull origin main' first")
                elif "could not read" in error_msg.lower() or "authentication" in error_msg.lower():
                    deployment_log.append("\n💡 Tip: Check your Git credentials or use SSH keys")
                
                return jsonify({
                    "status": "partial",
                    "message": "Files created and committed, but push failed",
                    "log": deployment_log,
                    "error": error_msg
                })
        else:
            # Manual deployment mode
            return jsonify({
                "status": "success",
                "message": "Files created successfully",
                "log": deployment_log,
                "instructions": """
Manual deployment steps:
1. git add docs/
2. git commit -m "Deploy to GitHub Pages"
3. git push origin main
"""
            })
        
    except subprocess.TimeoutExpired:
        deployment_log.append("❌ Operation timed out")
        return jsonify({
            "status": "error",
            "message": "Deployment timed out",
            "log": deployment_log
        })
    except Exception as e:
        deployment_log.append(f"❌ Error: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Deployment failed: {str(e)}",
            "log": deployment_log
        })


if __name__ == '__main__':
    # Use a secure port and enable debug mode for development
    app.run(debug=True, port=5000)
