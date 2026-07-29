"""CLI entrypoint for the RISC-V parameter extraction pipeline."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from src.extractor import ParameterExtractor
from src.models import AppConfig
from src.utils import configure_logging


def main() -> None:
    """Run extraction for every snippet in the input directory."""
    project_root = Path(__file__).resolve().parent
    load_dotenv(project_root / ".env")

    config = AppConfig.from_env(project_root=project_root)
    configure_logging(config.log_file)

    extractor = ParameterExtractor(config=config)

    processed_files = 0
    total_parameters = 0

    for input_file in sorted(config.input_dir.glob("*.txt")):
        print(f"Processing {input_file.name}")
        document = extractor.extract(input_file)
        output_file = config.output_dir / f"{input_file.stem}.yaml"
        extractor.save_output(document=document, output_path=output_file)

        parameter_count = len(document.parameters)
        processed_files += 1
        total_parameters += parameter_count
        print(f"Extracted {parameter_count} parameters")
        print()

    print("Finished")
    print(f"Processed: {processed_files} files")
    print(f"Total parameters: {total_parameters}")


if __name__ == "__main__":
    main()
