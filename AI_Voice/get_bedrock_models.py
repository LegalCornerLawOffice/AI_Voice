# list_bedrock_models.py
import boto3
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

# Load environment variables from .env
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

def list_bedrock_models():
    """List all available Bedrock models in your region"""
    
    # Get AWS config from environment
    region = os.getenv('AWS_REGION', 'us-west-2')
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')

    access_key_status = "set" if aws_access_key_id else "not set"
    
    # Check if credentials are set
    if not aws_access_key_id or not aws_secret_access_key:
        print("❌ AWS credentials not found in .env file")
        print("\nPlease add to your .env file:")
        print("AWS_ACCESS_KEY_ID=your_access_key")
        print("AWS_SECRET_ACCESS_KEY=your_secret_key")
        print("AWS_REGION=us-west-2")
        return
    
    print(f"🔑 Using credentials from .env")
    print(f"   Region: {region}")
    print(f"   Access Key: {access_key_status}")
    print()
    
    # Create client with credentials from .env
    try:
        client = boto3.client(
            'bedrock',
            region_name=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )
    except Exception as e:
        print(f"❌ Error creating Bedrock client: {e}")
        print("\nMake sure your .env file has:")
        print("1. AWS_ACCESS_KEY_ID=your_key")
        print("2. AWS_SECRET_ACCESS_KEY=your_secret")
        print("3. AWS_REGION=us-west-2")
        return
    
    try:
        response = client.list_foundation_models()
        
        models = []
        for model in response.get('modelSummaries', []):
            models.append({
                'Provider': model.get('modelName', '').split(' - ')[0] if ' - ' in model.get('modelName', '') else 'Unknown',
                'Model Name': model.get('modelName', 'Unknown'),
                'Model ID': model.get('modelId', 'N/A'),
                'Input Price/1M': model.get('inputTokenPrice', 'N/A'),
                'Output Price/1M': model.get('outputTokenPrice', 'N/A'),
            })
        
        # Sort by provider
        models.sort(key=lambda x: x['Provider'])
        
        print("\n" + "="*120)
        print(f"AVAILABLE BEDROCK MODELS ({region})")
        print("="*120 + "\n")
        
        if HAS_TABULATE:
            print(tabulate(models, headers='keys', tablefmt='grid'))
        else:
            # Fallback to simple printing if tabulate not available
            for model in models:
                print(f"\n{model['Provider']} - {model['Model Name']}")
                print(f"  Model ID: {model['Model ID']}")
                print(f"  Input:  {model['Input Price/1M']}/1M tokens")
                print(f"  Output: {model['Output Price/1M']}/1M tokens")
        
        print("\n" + "="*120)
        print("HOW TO USE:")
        print("="*120)
        print(f"""
1. Copy the "Model ID" from the table above
2. Update your .env file:
   
   AWS_BEDROCK_MODEL_ID=<paste_model_id_here>

3. Examples:
   AWS_BEDROCK_MODEL_ID=deepseek.deepseek-r1-distill-qwen-32b
   AWS_BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
   AWS_BEDROCK_MODEL_ID=meta.llama3-70b-instruct-v1:0

4. Restart your server:
   python main.py
   
Current config from .env:
   Region: {region}
   Model ID: {os.getenv('AWS_BEDROCK_MODEL_ID', 'Not set')}
""")
        
    except Exception as e:
        print(f"❌ Error listing models: {e}")
        print("\nPossible issues:")
        print("1. You may not have requested model access yet")
        print("2. Go to AWS Console → Bedrock → Model access")
        print("3. Click 'Modify model access' and request models")
        print("4. Wait 2-5 minutes for approval")

if __name__ == "__main__":
    list_bedrock_models()