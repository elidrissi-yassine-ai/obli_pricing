import requests
import pandas as pd
from io import StringIO
import urllib.parse


def download_bdt(date_courbe: str) -> pd.DataFrame:
    base_url = "https://www.bkam.ma/"
    date_encodee = urllib.parse.quote(date_courbe, safe="")

    export_url = (
        "https://www.bkam.ma/export/blockcsv/2340/"
        "c3367fcefc5f524397748201aee5dab8/"
        "e1d6b9bbf87f86f8ba53e8518e882982"
        f"?date={date_encodee}"
        "&block=e1d6b9bbf87f86f8ba53e8518e882982"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": base_url,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    }

    with requests.Session() as s:
        s.get(base_url, headers=headers, timeout=15)

        r = s.get(export_url, headers=headers, timeout=15)

        if r.status_code != 200:
            raise Exception(f"Erreur HTTP : {r.status_code}")

        content = r.text.strip()

        if not content or len(content) < 10:
            raise Exception(
                f"Réponse vide pour la date {date_courbe}. "
                "Vérifiez que la date est un jour ouvré et au format DD/MM/YYYY."
            )

        lines = content.splitlines()

        sep = ";" if lines[0].count(";") >= lines[0].count(",") else ","

        col_counts = [line.count(sep) for line in lines if line.strip()]
        max_cols = max(col_counts)

        header_idx = next(
            i for i, line in enumerate(lines)
            if line.strip() and line.count(sep) == max_cols
        )

        clean_content = "\n".join(lines[header_idx:])

        df = pd.read_csv(StringIO(clean_content), sep=sep)

        df.columns = df.columns.str.strip()

        for col in df.columns:
            if df[col].dtype == object:
                try:
                    df[col] = df[col].str.replace(",", ".").str.strip()
                    df[col] = pd.to_numeric(df[col], errors="ignore")
                except Exception:
                    pass

        return df
