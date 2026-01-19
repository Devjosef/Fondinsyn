import requests
import pandas as pd

def update_gist_csv(csv_path, gist_id, filename="data.csv", token=None):
    """Push to existing Github Gist """
    df = pd.read_csv(csv_path)
    csv_content = df.to_csv(index=False)

    url = f"https://api.github.com/gists/{gist_id}"
    headers = {"Authroization": f"token {token}"} if token else {}

    response = requests.patch(url, json={
        "files": {filename: {"content": csv_content}}
        }, headers=headers)
    
    print(f"Gist updated: {response.json()['html_url']}")

    update_gist_csv("local_data.csv", "gist_id_here", token="")