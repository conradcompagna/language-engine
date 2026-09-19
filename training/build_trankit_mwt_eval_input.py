from pathlib import Path


def collapse_mwt_conllu(src_path: Path, dst_path: Path) -> None:
    out_lines = []
    block = []

    def flush_sentence(lines):
        if not lines:
            return
        sent_out = []
        next_id = 1
        skip_until = None
        for line in lines:
            if line.startswith("#"):
                sent_out.append(line)
                continue
            cols = line.split("\t")
            if len(cols) != 10:
                sent_out.append(line)
                continue
            tok_id = cols[0]
            if "." in tok_id:
                continue
            if skip_until is not None:
                if "-" in tok_id:
                    continue
                try:
                    cur = int(tok_id)
                except ValueError:
                    continue
                if cur <= skip_until:
                    if cur == skip_until:
                        skip_until = None
                    continue
            if "-" in tok_id:
                start, end = tok_id.split("-", 1)
                skip_until = int(end)
                surface = cols[1]
                misc = cols[9]
                misc = "MWT=Yes" if misc in {"", "_"} else f"{misc}|MWT=Yes"
                sent_out.append(
                    "\t".join(
                        [
                            str(next_id),
                            surface,
                            "_",
                            "_",
                            "_",
                            "_",
                            "0" if next_id == 1 else str(next_id - 1),
                            "root" if next_id == 1 else "dep",
                            "_",
                            misc,
                        ]
                    )
                )
                next_id += 1
                continue

            sent_out.append(
                "\t".join(
                    [
                        str(next_id),
                        cols[1],
                        "_",
                        "_",
                        "_",
                        "_",
                        "0" if next_id == 1 else str(next_id - 1),
                        "root" if next_id == 1 else "dep",
                        "_",
                        cols[9] if cols[9] not in {"", "_"} else "_",
                    ]
                )
            )
            next_id += 1
        out_lines.extend(sent_out)
        out_lines.append("")

    with src_path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if line == "":
                flush_sentence(block)
                block = []
            else:
                block.append(line)

    if block:
        flush_sentence(block)

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    full_dir = root / "training" / "dcs_sanskrit_trankit_full"
    collapse_mwt_conllu(
        full_dir / "dev.conllu",
        full_dir / "dev.mwt_input.conllu",
    )


if __name__ == "__main__":
    main()
