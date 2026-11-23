from estat_pandas import load


def get_cpi_rate(start=None, end=None):
    """Load the cataloged national core CPI year-over-year rate."""
    data = load("JPN_CPI_CORE_YOY", start=start, end=end)
    return data[["DATE", "value"]].rename(columns={"value": "inflation"})


def main():
    data = get_cpi_rate()
    data.to_csv("cpi_inflation.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
