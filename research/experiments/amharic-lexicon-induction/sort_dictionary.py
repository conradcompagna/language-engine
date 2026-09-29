import pandas as pd

df = pd.read_csv("am_en_dictionary.tsv", sep="\t")
df["score"] = pd.to_numeric(df["score"], errors="coerce")
df = df.dropna(subset=["score"])
df = df.sort_values("score", ascending=False)
df.to_csv("am_en_dictionary.tsv", sep="\t", index=False)
print(f"Sorted {len(df)} rows by score descending.")
print(f"Score range: {df['score'].min():.4f} - {df['score'].max():.4f}")
print(f"Median score: {df['score'].median():.4f}")
print(df[['score','en_1']].head(20).to_string())
