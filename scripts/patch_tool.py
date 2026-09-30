import json, sys

def run(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    filepath = data['filepath']
    target = data['target']
    replacement = data['replacement']

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Normalize line endings for replacement
    content_norm = content.replace('
', '
')
    target_norm = target.replace('
', '
')
    replacement_norm = replacement.replace('
', '
')

    if target_norm not in content_norm:
        print(f"FAILED: target not found in {filepath}")
        sys.exit(1)

    updated = content_norm.replace(target_norm, replacement_norm, 1)
    with open(filepath, 'w', encoding='utf-8', newline='
') as f:
        f.write(updated)
    print(f"SUCCESS: updated {filepath}")

if __name__ == '__main__':
    run(sys.argv[1])
