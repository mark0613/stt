import argparse
import sys
from pathlib import Path

from src.stt import transcribe


def main() -> None:
    parser = argparse.ArgumentParser(description='將音檔轉成逐字稿 JSON')
    parser.add_argument('audio_file', type=Path, help='音檔路徑')
    parser.add_argument('output_dir', type=Path, nargs='?', help='輸出目錄（預設與音檔同目錄）')
    parser.add_argument('-n', '--num-speakers', type=int, help='說話者人數，會帶入 prompt')
    parser.add_argument('-p', '--prompt', help='額外說明，會帶入 prompt')
    args = parser.parse_args()

    input_path = args.audio_file
    output_dir = args.output_dir if args.output_dir else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'{input_path.stem}.json'

    try:
        transcribe(
            input_path,
            output_path=output_path,
            speaker_count=args.num_speakers,
            extra_instructions=args.prompt,
        )
    except Exception as error:
        print(f'STT failed: {error}')
        sys.exit(1)

    print(f'Transcript saved to {output_path}')


if __name__ == '__main__':
    main()
