"""Quick local testing without an MCP client."""
import argparse
import json
from research_core import index_all, list_documents, search_documents, answer_question

parser = argparse.ArgumentParser(description='Local research document CLI')
parser.add_argument('command', choices=['index', 'list', 'search', 'ask'])
parser.add_argument('text', nargs='?', default='')
args = parser.parse_args()
if args.command in ('search','ask') and not args.text:
    parser.error('A question or search phrase is required')
functions = {'index': index_all, 'list': list_documents, 'search': lambda: search_documents(args.text),
             'ask': lambda: answer_question(args.text)}
print(json.dumps(functions[args.command](), ensure_ascii=False, indent=2))
