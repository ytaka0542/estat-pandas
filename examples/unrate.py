from estat_pandas import load


def get_unemployment_rate(start=None, end=None):
    """Load the cataloged national quarterly unemployment rate."""
    data = load("JPN_UNEMPLOYMENT_RATE", start=start, end=end)
    return data[["DATE", "value"]].rename(columns={"value": "unemployment"})


def main():
    data = get_unemployment_rate()
    data.to_csv("urate.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
