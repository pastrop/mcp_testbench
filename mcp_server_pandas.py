import arxiv
import json
import os
import pandas as pd
from typing import List
from mcp.server.fastmcp import FastMCP

#Service Functions:
#(1)Text cleanup
def text_input(file = 'Mejuri_texts.csv'):
  df = pd.read_csv(file)
  df_clean = df[df['Text'].apply(lambda x: isinstance(x, str))]
  texts = [item.replace("\t", " ") for item in df_clean['Text']]

  return texts


# Initialize FastMCP server
mcp = FastMCP("csv_tools")

@mcp.tool()
def csv_filtering(file: str = None) -> List[str]:
    """
   Description of the function
    
    Args:
        
        
    Returns:
        
    """
    

    if file == None:
        file_path = "/Users/alexsmirnoff/Documents/data/alpha_test_small.csv"
    else:
        file_path = file

    # Try to load existing papers info
    try:
        with open(file_path, "r") as json_file:
            papers_info = json.load(json_file)
    except (FileNotFoundError):
        df = None



    
    return 

@mcp.tool()
def extract_info(paper_id: str) -> str:
    """
    Search for information about a specific paper across all topic directories.
    
    Args:
        paper_id: The ID of the paper to look for
        
    Returns:
        JSON string with paper information if found, error message if not found
    """
 
    for item in os.listdir(PAPER_DIR):
        item_path = os.path.join(PAPER_DIR, item)
        if os.path.isdir(item_path):
            file_path = os.path.join(item_path, "papers_info.json")
            if os.path.isfile(file_path):
                try:
                    with open(file_path, "r") as json_file:
                        papers_info = json.load(json_file)
                        if paper_id in papers_info:
                            return json.dumps(papers_info[paper_id], indent=2)
                except (FileNotFoundError, json.JSONDecodeError) as e:
                    print(f"Error reading {file_path}: {str(e)}")
                    continue
    
    return f"There's no saved information related to paper {paper_id}."



if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')