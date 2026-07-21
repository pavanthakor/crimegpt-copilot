# Judgment Corpus — Verification Worksheet

Source: `data/judgments/judgments.jsonl` (41 entries). One row per judgment, checked against
Indian Kanoon.

## Verification pass — 2026-07-21

All **41** citations verified against Indian Kanoon. **1 correction** made:

- **Row 23 — Shafhi Mohammad v. State of Himachal Pradesh:** citation was `(2018) 5 SCC 311`,
  corrected to **`(2018) 2 SCC 807`** (case name and year were already correct). The judgments
  ChromaDB collection was re-ingested (`python -m app.ai.judgments --reset`) so the embedded
  text and metadata carry the corrected citation.

The remaining 40 citations were confirmed correct as recorded. Each row's status is noted in the
`Verified?` column below.

**⚠ Every `source_url` in the corpus is a generic Indian Kanoon _search_ link, not a specific
document URL** — the flag ⚠ marks this on each row. Locate the exact `indiankanoon.org/doc/<id>/`
page and note it in the last column if a document-specific URL is later substituted.

Sort order: theft / snatching / robbery / recent-possession first, then arrest·remand, then
evidence, then the rest (FIR / investigation).

| # | Case title | Citation | Court | Year | Source URL | Verified? | Correct value if wrong |
|---|---|---|---|---|---|---|---|
|  1 | Gulab Chand v. State of Madhya Pradesh | (1995) 3 SCC 574 | Supreme Court of India | 1995 | [⚠ search](https://indiankanoon.org/search/?formInput=Gulab%20Chand%20v%20State%20of%20Madhya%20Pradesh) | ✅ correct (Indian Kanoon) |  |
|  2 | Trimbak v. State of Madhya Pradesh | AIR 1954 SC 39 | Supreme Court of India | 1954 | [⚠ search](https://indiankanoon.org/search/?formInput=Trimbak%20v%20State%20of%20Madhya%20Pradesh) | ✅ correct (Indian Kanoon) |  |
|  3 | Pyare Lal Bhargava v. State of Rajasthan | AIR 1963 SC 1094 | Supreme Court of India | 1963 | [⚠ search](https://indiankanoon.org/search/?formInput=Pyare%20Lal%20Bhargava%20v%20State%20of%20Rajasthan) | ✅ correct (Indian Kanoon) |  |
|  4 | K.N. Mehra v. State of Rajasthan | AIR 1957 SC 369 | Supreme Court of India | 1957 | [⚠ search](https://indiankanoon.org/search/?formInput=K.N.%20Mehra%20v%20State%20of%20Rajasthan) | ✅ correct (Indian Kanoon) |  |
|  5 | Sharad Birdhichand Sarda v. State of Maharashtra | (1984) 4 SCC 116 | Supreme Court of India | 1984 | [⚠ search](https://indiankanoon.org/search/?formInput=Sharad%20Birdhichand%20Sarda%20v%20State%20of%20Maharashtra) | ✅ correct (Indian Kanoon) |  |
|  6 | Arnesh Kumar v. State of Bihar | (2014) 8 SCC 273 | Supreme Court of India | 2014 | [⚠ search](https://indiankanoon.org/search/?formInput=Arnesh%20Kumar%20v%20State%20of%20Bihar) | ✅ correct (Indian Kanoon) |  |
|  7 | Joginder Kumar v. State of Uttar Pradesh | (1994) 4 SCC 260 | Supreme Court of India | 1994 | [⚠ search](https://indiankanoon.org/search/?formInput=Joginder%20Kumar%20v%20State%20of%20Uttar%20Pradesh) | ✅ correct (Indian Kanoon) |  |
|  8 | D.K. Basu v. State of West Bengal | (1997) 1 SCC 416 | Supreme Court of India | 1997 | [⚠ search](https://indiankanoon.org/search/?formInput=D.K.%20Basu%20v%20State%20of%20West%20Bengal) | ✅ correct (Indian Kanoon) |  |
|  9 | Siddharth v. State of Uttar Pradesh | (2022) 1 SCC 676 | Supreme Court of India | 2021 | [⚠ search](https://indiankanoon.org/search/?formInput=Siddharth%20v%20State%20of%20Uttar%20Pradesh%202021) | ✅ correct (Indian Kanoon) |  |
| 10 | Satender Kumar Antil v. Central Bureau of Investigation | (2022) 10 SCC 51 | Supreme Court of India | 2022 | [⚠ search](https://indiankanoon.org/search/?formInput=Satender%20Kumar%20Antil%20v%20CBI) | ✅ correct (Indian Kanoon) |  |
| 11 | Rakesh Kumar Paul v. State of Assam | (2017) 15 SCC 67 | Supreme Court of India | 2017 | [⚠ search](https://indiankanoon.org/search/?formInput=Rakesh%20Kumar%20Paul%20v%20State%20of%20Assam) | ✅ correct (Indian Kanoon) |  |
| 12 | Bikramjit Singh v. State of Punjab | (2020) 10 SCC 616 | Supreme Court of India | 2020 | [⚠ search](https://indiankanoon.org/search/?formInput=Bikramjit%20Singh%20v%20State%20of%20Punjab) | ✅ correct (Indian Kanoon) |  |
| 13 | Sanjay Chandra v. Central Bureau of Investigation | (2012) 1 SCC 40 | Supreme Court of India | 2012 | [⚠ search](https://indiankanoon.org/search/?formInput=Sanjay%20Chandra%20v%20CBI) | ✅ correct (Indian Kanoon) |  |
| 14 | Gurbaksh Singh Sibbia v. State of Punjab | (1980) 2 SCC 565 | Supreme Court of India | 1980 | [⚠ search](https://indiankanoon.org/search/?formInput=Gurbaksh%20Singh%20Sibbia%20v%20State%20of%20Punjab) | ✅ correct (Indian Kanoon) |  |
| 15 | Prem Shankar Shukla v. Delhi Administration | (1980) 3 SCC 526 | Supreme Court of India | 1980 | [⚠ search](https://indiankanoon.org/search/?formInput=Prem%20Shankar%20Shukla%20v%20Delhi%20Administration) | ✅ correct (Indian Kanoon) |  |
| 16 | Sunil Batra v. Delhi Administration | (1978) 4 SCC 494 | Supreme Court of India | 1978 | [⚠ search](https://indiankanoon.org/search/?formInput=Sunil%20Batra%20v%20Delhi%20Administration) | ✅ correct (Indian Kanoon) |  |
| 17 | Pulukuri Kottaya v. Emperor | AIR 1947 PC 67 | Privy Council | 1947 | [⚠ search](https://indiankanoon.org/search/?formInput=Pulukuri%20Kottaya%20v%20Emperor) | ✅ correct (Indian Kanoon) |  |
| 18 | Mohd. Inayatullah v. State of Maharashtra | (1976) 1 SCC 828 | Supreme Court of India | 1976 | [⚠ search](https://indiankanoon.org/search/?formInput=Mohd.%20Inayatullah%20v%20State%20of%20Maharashtra) | ✅ correct (Indian Kanoon) |  |
| 19 | State of Uttar Pradesh v. Deoman Upadhyaya | AIR 1960 SC 1125 | Supreme Court of India | 1960 | [⚠ search](https://indiankanoon.org/search/?formInput=State%20of%20U.P.%20v%20Deoman%20Upadhyaya) | ✅ correct (Indian Kanoon) |  |
| 20 | State of Rajasthan v. Teja Ram | (1999) 3 SCC 507 | Supreme Court of India | 1999 | [⚠ search](https://indiankanoon.org/search/?formInput=State%20of%20Rajasthan%20v%20Teja%20Ram) | ✅ correct (Indian Kanoon) |  |
| 21 | Anvar P.V. v. P.K. Basheer | (2014) 10 SCC 473 | Supreme Court of India | 2014 | [⚠ search](https://indiankanoon.org/search/?formInput=Anvar%20P.V.%20v%20P.K.%20Basheer) | ✅ correct (Indian Kanoon) |  |
| 22 | Arjun Panditrao Khotkar v. Kailash Kushanrao Gorantyal | (2020) 7 SCC 1 | Supreme Court of India | 2020 | [⚠ search](https://indiankanoon.org/search/?formInput=Arjun%20Panditrao%20Khotkar%20v%20Kailash%20Kushanrao%20Gorantyal) | ✅ correct (Indian Kanoon) |  |
| 23 | Shafhi Mohammad v. State of Himachal Pradesh | (2018) 2 SCC 807 | Supreme Court of India | 2018 | [⚠ search](https://indiankanoon.org/search/?formInput=Shafhi%20Mohammad%20v%20State%20of%20Himachal%20Pradesh) | ✅ corrected (Indian Kanoon) | was (2018) 5 SCC 311 → (2018) 2 SCC 807 |
| 24 | State (NCT of Delhi) v. Navjot Sandhu | (2005) 11 SCC 600 | Supreme Court of India | 2005 | [⚠ search](https://indiankanoon.org/search/?formInput=State%20NCT%20of%20Delhi%20v%20Navjot%20Sandhu) | ✅ correct (Indian Kanoon) |  |
| 25 | Malkhansingh v. State of Madhya Pradesh | (2003) 5 SCC 746 | Supreme Court of India | 2003 | [⚠ search](https://indiankanoon.org/search/?formInput=Malkhansingh%20v%20State%20of%20Madhya%20Pradesh) | ✅ correct (Indian Kanoon) |  |
| 26 | Dana Yadav alias Dahu v. State of Bihar | (2002) 7 SCC 295 | Supreme Court of India | 2002 | [⚠ search](https://indiankanoon.org/search/?formInput=Dana%20Yadav%20v%20State%20of%20Bihar) | ✅ correct (Indian Kanoon) |  |
| 27 | Vadivelu Thevar v. State of Madras | AIR 1957 SC 614 | Supreme Court of India | 1957 | [⚠ search](https://indiankanoon.org/search/?formInput=Vadivelu%20Thevar%20v%20State%20of%20Madras) | ✅ correct (Indian Kanoon) |  |
| 28 | Sat Paul v. Delhi Administration | (1976) 1 SCC 727 | Supreme Court of India | 1976 | [⚠ search](https://indiankanoon.org/search/?formInput=Sat%20Paul%20v%20Delhi%20Administration) | ✅ correct (Indian Kanoon) |  |
| 29 | Appabhai v. State of Gujarat | AIR 1988 SC 696 | Supreme Court of India | 1988 | [⚠ search](https://indiankanoon.org/search/?formInput=Appabhai%20v%20State%20of%20Gujarat) | ✅ correct (Indian Kanoon) |  |
| 30 | Masalti v. State of Uttar Pradesh | AIR 1965 SC 202 | Supreme Court of India | 1965 | [⚠ search](https://indiankanoon.org/search/?formInput=Masalti%20v%20State%20of%20Uttar%20Pradesh) | ✅ correct (Indian Kanoon) |  |
| 31 | Hanumant v. State of Madhya Pradesh | AIR 1952 SC 343 | Supreme Court of India | 1952 | [⚠ search](https://indiankanoon.org/search/?formInput=Hanumant%20v%20State%20of%20Madhya%20Pradesh) | ✅ correct (Indian Kanoon) |  |
| 32 | Nandini Satpathy v. P.L. Dani | (1978) 2 SCC 424 | Supreme Court of India | 1978 | [⚠ search](https://indiankanoon.org/search/?formInput=Nandini%20Satpathy%20v%20P.L.%20Dani) | ✅ correct (Indian Kanoon) |  |
| 33 | Selvi v. State of Karnataka | (2010) 7 SCC 263 | Supreme Court of India | 2010 | [⚠ search](https://indiankanoon.org/search/?formInput=Selvi%20v%20State%20of%20Karnataka) | ✅ correct (Indian Kanoon) |  |
| 34 | Ritesh Sinha v. State of Uttar Pradesh | (2019) 8 SCC 1 | Supreme Court of India | 2019 | [⚠ search](https://indiankanoon.org/search/?formInput=Ritesh%20Sinha%20v%20State%20of%20Uttar%20Pradesh) | ✅ correct (Indian Kanoon) |  |
| 35 | State of Punjab v. Baldev Singh | (1999) 6 SCC 172 | Supreme Court of India | 1999 | [⚠ search](https://indiankanoon.org/search/?formInput=State%20of%20Punjab%20v%20Baldev%20Singh) | ✅ correct (Indian Kanoon) |  |
| 36 | State of Punjab v. Balbir Singh | (1994) 3 SCC 299 | Supreme Court of India | 1994 | [⚠ search](https://indiankanoon.org/search/?formInput=State%20of%20Punjab%20v%20Balbir%20Singh) | ✅ correct (Indian Kanoon) |  |
| 37 | Directorate of Revenue v. Mohammed Nisar Holia | (2008) 2 SCC 370 | Supreme Court of India | 2008 | [⚠ search](https://indiankanoon.org/search/?formInput=Directorate%20of%20Revenue%20v%20Mohammed%20Nisar%20Holia) | ✅ correct (Indian Kanoon) |  |
| 38 | Lalita Kumari v. Government of Uttar Pradesh | (2014) 2 SCC 1 | Supreme Court of India | 2014 | [⚠ search](https://indiankanoon.org/search/?formInput=Lalita%20Kumari%20v%20Government%20of%20Uttar%20Pradesh) | ✅ correct (Indian Kanoon) |  |
| 39 | State of Haryana v. Bhajan Lal | 1992 Supp (1) SCC 335 | Supreme Court of India | 1992 | [⚠ search](https://indiankanoon.org/search/?formInput=State%20of%20Haryana%20v%20Bhajan%20Lal) | ✅ correct (Indian Kanoon) |  |
| 40 | Thulia Kali v. State of Tamil Nadu | (1972) 3 SCC 393 | Supreme Court of India | 1972 | [⚠ search](https://indiankanoon.org/search/?formInput=Thulia%20Kali%20v%20State%20of%20Tamil%20Nadu) | ✅ correct (Indian Kanoon) |  |
| 41 | H.N. Rishbud v. State of Delhi | AIR 1955 SC 196 | Supreme Court of India | 1955 | [⚠ search](https://indiankanoon.org/search/?formInput=H.N.%20Rishbud%20v%20State%20of%20Delhi) | ✅ correct (Indian Kanoon) |  |
