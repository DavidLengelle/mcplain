"""Entry point of the atelier container: analyze /job/input offline and print one JSON line on stdout"""

import argparse
import contextlib
import sys
import traceback
from pathlib import Path

from mcplain.analyze import analyze_job

JOB_INPUT = "/job/input"
WORK_DIR = "/work"
EXIT_RESULT = 0
EXIT_NO_RESULT = 1


def main(argv: list[str] | None = None) -> int:
    """Write the AnalysisResult as one JSON line on stdout and return 0, or return 1 when there is no result"""

    parser = argparse.ArgumentParser(prog="mcplain-analyze")
    parser.add_argument("--input", default=JOB_INPUT)
    parser.add_argument("--work", default=WORK_DIR)
    options = parser.parse_args(argv)
    stdout = sys.stdout.buffer
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = analyze_job(Path(options.input), Path(options.work))
            line = result.model_dump_json().encode("utf-8") + b"\n"
    except Exception as error:
        frame = traceback.extract_tb(error.__traceback__)[-1]
        print(f"mcplain-analyze: {type(error).__name__} at {Path(frame.filename).name}:{frame.lineno}", file=sys.stderr)
        return EXIT_NO_RESULT
    stdout.write(line)
    stdout.flush()
    return EXIT_RESULT


if __name__ == "__main__":
    sys.exit(main())
