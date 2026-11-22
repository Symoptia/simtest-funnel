# Open-Meteo sample: attribution

[Weather data by Open-Meteo.com](https://open-meteo.com/)

`stockholm-2026-11-05-to-19.csv` is a response of Open-Meteo's
[Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api),
licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (Attribution
4.0 International) as stated on Open-Meteo's
[licence page](https://open-meteo.com/en/licence).

- **Weather model:** ECMWF IFS HRES 9 km (`models=ecmwf_ifs`), forecasts by
  the European Centre for Medium-Range Weather Forecasts
  ([ECMWF](https://www.ecmwf.int/)), listed under CC-BY on Open-Meteo's
  licence page.
- **Location:** Stockholm (requested `latitude=59.3293`,
  `longitude=18.0686`; Open-Meteo answered for its grid point 59.36731 N,
  18.0 E, elevation 24 m).
- **Contents:** hourly `temperature_2m` of the latest run and the forecasts
  made 1, 3 and 5 days before each hour (`temperature_2m_previous_day1`,
  `_previous_day3`, `_previous_day5`), 2026-11-05T00:00 to 2026-11-19T23:00,
  times in GMT (ISO 8601 without offset), 360 rows.
- **Request:**

  ```text
  https://previous-runs-api.open-meteo.com/v1/forecast?latitude=59.3293&longitude=18.0686&hourly=temperature_2m,temperature_2m_previous_day1,temperature_2m_previous_day3,temperature_2m_previous_day5&models=ecmwf_ifs&start_date=2026-11-05&end_date=2026-11-19&format=csv
  ```

- **Retrieved:** 2026-11-22 (16:44 UTC), once, with `curl`.
- **SHA-256:** `19b71b3a1d68078dca228a14d8b7ef279801a7430968a71a3a7745a70b0d6444`
  (12 226 bytes).
- **Changes:** none. The file is byte-identical to the API response,
  including its three-line metadata preamble (so the header is on line 4).

## Caveats

- The "actual" column (`temperature_2m`) is the latest model run / analysis
  of the weather model, not station measurements.
- Open-Meteo may reprocess archived runs, so the same request made later
  can return slightly different bytes; the SHA-256 above identifies the
  copy kept here.
- Open-Meteo's free API is for non-commercial use only and limited to fewer
  than 10,000 calls a day (5,000 an hour, 600 a minute); see its
  [terms](https://open-meteo.com/en/terms). Commercial use needs one of
  Open-Meteo's paid plans.

The sample lives in this repository only; it is not part of any published
package.
