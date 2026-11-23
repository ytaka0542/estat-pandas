from estat_pandas import load


def main():
    data = load(
        "JPN_CALL_RATE_OVERNIGHT",
        start="2024-01-01",
        end="2024-12-31",
    )
    data.to_csv("boj_call_rate.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
