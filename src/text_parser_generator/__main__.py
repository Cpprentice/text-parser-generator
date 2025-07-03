import argparse
from pathlib import Path
import sys

from text_parser_generator import TextParserGenerator, load_specification_from_yaml


def get_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a text parser from a YAML specifiaction document"
    )
    parser.add_argument(
        "specification",
        type=Path,
        help="Path to the YAML specification file."
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path.cwd(),
        help="Path to the output folder (default: .)"
    )
    return parser


def main():
    arg_parser = get_argument_parser()
    args = arg_parser.parse_args()

    if not args.specification.is_file():
        print(f"Error: File '{args.specification}' does not exist or is not a file.", file=sys.stderr)
        sys.exit(1)

    if not args.output.is_dir():
        print(f'Error: Output path "{args.output}" does not exist or is no directory.', file=sys.stderr)
        sys.exit(1)
    
    spec = load_specification_from_yaml(args.specification.read_text())
    generator = TextParserGenerator(spec, args.output)
    generator.run()


if __name__ == '__main__':
    main()
