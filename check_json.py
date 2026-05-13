import json

with open('data/product_master.json', 'r', encoding='utf-8') as f:
    content = f.read()
    print(f'File size: {len(content)} bytes')
    print(f'Last 100 chars: {repr(content[-100:])}')
    try:
        data = json.loads(content)
        print(f'JSON parsing successful! Items: {len(data)}')
    except json.JSONDecodeError as e:
        print(f'JSON parsing failed: {e}')
        print(f'Error at line {e.lineno}, column {e.colno}')
        start = max(0, e.pos - 100)
        end = min(len(content), e.pos + 100)
        print(f'Content around error:\n{repr(content[start:end])}')
