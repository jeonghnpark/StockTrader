import json
import sys

try:
    with open('data/product_master.json', 'r', encoding='utf-8') as f:
        content = f.read()
        
    print(f"Total file size: {len(content)} bytes")
    print(f"Total lines: {content.count(chr(10)) + 1}")
    
    # 마지막 100자 확인
    print(f"\nLast 100 characters:")
    print(repr(content[-100:]))
    
    # JSON 파싱 시도
    data = json.loads(content)
    print(f"\n✓ JSON is valid!")
    print(f"✓ Total items: {len(data)}")
    
except json.JSONDecodeError as e:
    print(f"\n✗ JSON Error: {e}")
    print(f"✗ Error at line {e.lineno}, column {e.colno}, position {e.pos}")
    
    # 에러 위치 주변 컨텍스트 출력
    start = max(0, e.pos - 200)
    end = min(len(content), e.pos + 100)
    
    print(f"\nContent around error position (char {e.pos}):")
    print("=" * 80)
    print(content[start:end])
    print("=" * 80)
    
    # 정확한 에러 위치 표시
    lines = content[:e.pos].split('\n')
    error_line = lines[-1] if lines else ""
    print(f"\nError line content: {repr(error_line)}")
    print(f"Next 50 chars from error: {repr(content[e.pos:e.pos+50])}")
    
    sys.exit(1)

except Exception as e:
    print(f"\n✗ Unexpected error: {e}")
    sys.exit(1)
