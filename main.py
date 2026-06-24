import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from src.logging_setup import setup_logging
from src.stt import ProgressHooks, transcribe


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

    console = Console()
    log_path = setup_logging(input_path)

    try:
        _run_with_progress(
            console,
            input_path,
            output_path,
            speaker_count=args.num_speakers,
            extra_instructions=args.prompt,
        )
    except Exception as error:
        console.print(f'[bold red]轉錄失敗：[/bold red]{error}')
        console.print(f'[dim]詳細 log：\n{log_path}[/dim]')
        sys.exit(1)

    console.print(f'[bold green]完成[/bold green] 逐字稿已存到 {output_path}')
    console.print(f'[dim]詳細 log：\n{log_path}[/dim]')


def _run_with_progress(
    console: Console,
    input_path: Path,
    output_path: Path,
    speaker_count: int | None,
    extra_instructions: str | None,
) -> None:
    progress = Progress(
        TextColumn('[progress.description]{task.description}'),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    with progress:
        upload_task = progress.add_task('上傳', total=None)
        transcribe_task = progress.add_task('轉錄', total=None)

        def on_chunks_ready(n: int) -> None:
            progress.update(upload_task, total=n)
            progress.update(transcribe_task, total=n)

        hooks = ProgressHooks(
            on_chunks_ready=on_chunks_ready,
            on_upload_done=lambda: progress.advance(upload_task),
            on_chunk_done=lambda: progress.advance(transcribe_task),
        )

        transcribe(
            input_path,
            output_path=output_path,
            speaker_count=speaker_count,
            extra_instructions=extra_instructions,
            hooks=hooks,
        )


if __name__ == '__main__':
    main()
