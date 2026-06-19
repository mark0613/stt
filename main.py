import sys
from pathlib import Path

from src.stt import transcribe

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python main.py <audio_file> [output_dir]')
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'{input_path.stem}.json'

    try:
        transcribe(input_path, output_path=output_path)
    except Exception as error:
        print(f'STT failed: {error}')
        sys.exit(1)

    print(f'Transcript saved to {output_path}')
