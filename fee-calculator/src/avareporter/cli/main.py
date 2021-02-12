import argparse

from avareporter.cli import all_scripts, script_by_name
import avareporter.scripts


def parse_args() -> argparse.Namespace:
    script_names = all_scripts()
    parser = argparse.ArgumentParser()

    parser.add_argument('script',
                        choices=script_names,
                        help='The name of the script to execute')

    args, _ = parser.parse_known_args()
    return args


def cmain():
    main(parse_args())


def main(args: argparse.Namespace):
    script = script_by_name(args.script)

    script()


if __name__ == "__main__":
    cmain()
