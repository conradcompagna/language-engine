"""
Training monitor for Ancient Greek tokenizer.
Runs trankit training in a subprocess and monitors the log file.
Kills the run if token F1 is not improving after 3 complete epochs.
"""

import subprocess
import sys
import os
import time
import re
import shutil
from pathlib import Path

BASE = Path(r"C:\Users\conra\Desktop\universal - js hybrid")
SAVE_DIR = BASE / "training" / "t_grc10k_tok1"
CUSTOMIZED_DIR = SAVE_DIR / "xlm-roberta-base" / "customized"
LOG_FILE = CUSTOMIZED_DIR / "logs" / "tokenize.training"
TRAIN_TXT = BASE / "training" / "perseus" / "grc_trankit_sampled_10000" / "splits_txt" / "train.txt"
TRAIN_CONLLU = (
    BASE / "training" / "perseus" / "grc_trankit_sampled_10000" / "splits" / "train.conllu"
)
DEV_TXT = BASE / "training" / "perseus" / "grc_trankit_sampled_10000" / "splits_txt" / "dev.txt"
DEV_CONLLU = BASE / "training" / "perseus" / "grc_trankit_sampled_10000" / "splits" / "dev.conllu"


def clean_stale_files():
    """Remove stale prediction and character files before training."""
    files_to_remove = [
        CUSTOMIZED_DIR / "preds" / "tokenizer.dev.conllu",
        CUSTOMIZED_DIR / "train.txt.character",
        CUSTOMIZED_DIR / "dev.txt.character",
    ]
    for f in files_to_remove:
        if f.exists():
            print(f"Removing stale: {f}")
            f.unlink()


def parse_scores_from_log():
    """Parse epoch token/sentence F1 scores from the training log."""
    if not LOG_FILE.exists():
        return []

    content = LOG_FILE.read_text(encoding="utf-8", errors="replace")

    scores = []
    epoch_re = re.compile(r"Best dev CoNLLu score: epoch (\d+)")
    tokens_re = re.compile(r"Tokens\s+\|\s+([\d.]+)\s+\|\s+([\d.]+)\s+\|\s+([\d.]+)")
    sentences_re = re.compile(r"Sentences\s+\|\s+([\d.]+)\s+\|\s+([\d.]+)\s+\|\s+([\d.]+)")

    chunks = content.split("Best dev CoNLLu score:")
    for chunk in chunks[1:]:
        epoch_m = epoch_re.search(chunk[:50])
        tokens_m = tokens_re.search(chunk[:300])
        sents_m = sentences_re.search(chunk[:300])
        if epoch_m and tokens_m:
            epoch = int(epoch_m.group(1))
            tok_f1 = float(tokens_m.group(3))
            sent_f1 = float(sents_m.group(3)) if sents_m else 0.0
            scores.append((epoch, tok_f1, sent_f1))

    return scores


def count_complete_epochs():
    """Count how many complete epoch evaluations are in the log."""
    return len(parse_scores_from_log())


def check_should_abort(scores):
    """
    Returns (should_abort, reason) based on score progression.
    Only abort if we have >=3 complete epochs and no improvement at all.
    """
    if len(scores) < 3:
        return False, None

    # Check last 3 epochs
    recent = scores[-3:]
    tok_scores = [s[1] for s in recent]

    # If best token F1 in last 3 epochs is < 20%, something is very wrong
    if max(tok_scores) < 20.0:
        return True, f"Token F1 stuck below 20% for 3 epochs: {tok_scores}"

    # If we have 6 epochs and max token F1 is still < 40%, abort
    if len(scores) >= 6 and max(s[1] for s in scores) < 40.0:
        return True, f"Token F1 below 40% after 6 epochs: max={max(s[1] for s in scores):.1f}%"

    return False, None


def run_training():
    """Start the trankit training process."""
    cmd = [
        sys.executable,
        "-X",
        "utf8",
        "-c",
        f"""import trankit; trankit.TPipeline(training_config={{
            'category': 'customized',
            'task': 'tokenize',
            'save_dir': r'{SAVE_DIR}',
            'train_txt_fpath': r'{TRAIN_TXT}',
            'train_conllu_fpath': r'{TRAIN_CONLLU}',
            'dev_txt_fpath': r'{DEV_TXT}',
            'dev_conllu_fpath': r'{DEV_CONLLU}',
        }}).train()""",
    ]

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"

    print(f"\nStarting training process...")
    print(f"Save dir: {SAVE_DIR}")
    print(f"Train: {TRAIN_TXT}")
    print(f"Dev: {DEV_TXT}")
    print(f"Log: {LOG_FILE}")
    print("-" * 60)

    # Write stdout/stderr to a separate output log
    out_log = SAVE_DIR / "xlm-roberta-base" / "customized" / "logs" / "train_stdout.log"
    out_log.parent.mkdir(parents=True, exist_ok=True)

    with open(out_log, "w", encoding="utf-8") as fout:
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=fout,
            stderr=subprocess.STDOUT,
            cwd=str(BASE),
        )

    return proc


def monitor_training(proc):
    """Monitor training and check scores every 2 minutes."""
    POLL_INTERVAL = 120  # seconds between checks
    last_epoch_count = 0
    consecutive_no_progress_checks = 0

    print("Monitoring training. Checking every 2 minutes...")
    print("Will abort if token F1 is stuck below thresholds.\n")

    while True:
        # Check if process finished
        retcode = proc.poll()
        if retcode is not None:
            print(f"\nTraining process finished with code: {retcode}")
            break

        # Sleep before checking
        time.sleep(POLL_INTERVAL)

        # Parse scores
        scores = parse_scores_from_log()
        new_epoch_count = len(scores)

        if new_epoch_count > last_epoch_count:
            # New epochs completed
            for i in range(last_epoch_count, new_epoch_count):
                ep, tok, sent = scores[i]
                print(f"[Epoch {ep:3d}] Tokens F1: {tok:6.2f}%  Sentences F1: {sent:6.2f}%")
            last_epoch_count = new_epoch_count

            # Check abort conditions
            should_abort, reason = check_should_abort(scores)
            if should_abort:
                print(f"\nABORTING: {reason}")
                proc.terminate()
                time.sleep(5)
                if proc.poll() is None:
                    proc.kill()
                return False  # Training failed

            # Check success
            best_tok = max(s[1] for s in scores)
            if best_tok >= 90.0:
                print(f"\nTarget reached! Best token F1: {best_tok:.2f}%")
                # Let training continue to completion for even better results
        else:
            print(f"  (waiting for next epoch... {new_epoch_count} complete so far)")

    # Final score report
    scores = parse_scores_from_log()
    if scores:
        best = max(scores, key=lambda x: x[1])
        print(
            f"\nFinal best: Epoch {best[0]}, Tokens F1: {best[1]:.2f}%, Sentences F1: {best[2]:.2f}%"
        )
        return best[1] >= 90.0
    return False


def main():
    print("=" * 60)
    print("Ancient Greek Tokenizer Training Monitor")
    print("=" * 60)

    # Clean stale files
    clean_stale_files()

    # Run training
    proc = run_training()

    # Monitor
    success = monitor_training(proc)

    if success:
        print("\nSUCCESS: Model trained with 90%+ token F1!")
        print(f"Model saved to: {CUSTOMIZED_DIR}")
    else:
        print("\nTraining did not reach 90% target.")
        print("Check logs for details.")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
