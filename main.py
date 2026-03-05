import json
import sys
from pathlib import Path

import src.config
from src.services import stt

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('❌ Usage: python main.py <audio_file> [output_dir]')
        sys.exit(1)
    # file
    input_path = Path(sys.argv[1])
    # path
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path.parent

    file_name = input_path.stem
    output_path = output_path / f'{file_name}.json'

    response = stt(input_path)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(response, f, ensure_ascii=False, indent=2)
    print(f'✅ Transcript saved to {output_path}')
