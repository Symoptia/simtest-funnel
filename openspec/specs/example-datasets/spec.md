# example-datasets Specification

## Purpose
Example data kept in the repository so that documentation walkthroughs and
tests run offline: the Open-Meteo forecast-against-latest-run sample, its
attribution, the matching live URLs and the README walkthrough.

## Requirements

### Requirement: Bundled Open-Meteo sample

The repository SHALL contain one CSV file from Open-Meteo's Previous Runs
API for one location: 15 days of hourly `temperature_2m` and its day-1, day-3
and day-5 previous-run columns, from one pinned weather model whose data is
licensed CC BY 4.0, for a fixed past date range, in GMT with ISO 8601 times,
kept byte-identical to the API response.

#### Scenario: Describe the sample
- **WHEN** an agent describes the sample file with header line 4
- **THEN** the result reports the time column `time` as a zone-less
  date-time column with 360 uniformly hourly rows, and the signal columns
  `temperature_2m (°C)`, `temperature_2m_previous_day1 (°C)`,
  `temperature_2m_previous_day3 (°C)` and
  `temperature_2m_previous_day5 (°C)`

#### Scenario: Same bytes as the documented request
- **WHEN** a maintainer compares the sample's SHA-256 with the one recorded
  in its attribution file
- **THEN** they are equal

### Requirement: Sample attribution

Next to the sample, an attribution file SHALL state "Weather data by
Open-Meteo.com" with a link to `https://open-meteo.com/`, the licence CC BY
4.0 with a link to it, the weather model and its provider, the exact request
URL, the retrieval date, the file's SHA-256 and that the data were not
changed. Every document using the sample SHALL carry the same credit line.

#### Scenario: Attribution present
- **WHEN** a reader opens the sample's folder
- **THEN** it contains the attribution file with the credit line, licence
  link, model, request URL, retrieval date and SHA-256

#### Scenario: README walkthrough credits the data
- **WHEN** a reader reads the walkthrough in the MCP server README
- **THEN** it shows "Weather data by Open-Meteo.com" linked to
  `https://open-meteo.com/` and names CC BY 4.0

### Requirement: Sample kept out of published packages

The sample and its attribution SHALL be part of the repository only and
SHALL NOT be included in any published package (wheel, sdist or npm
package).

#### Scenario: Built packages
- **WHEN** the MCP server's wheel and sdist are built
- **THEN** neither contains the sample CSV

### Requirement: Forecast walkthrough

The MCP server README SHALL contain a walkthrough "was the forecast made N
days ahead close enough?" on the bundled sample: describe it with header
line 4, compare `temperature_2m (°C)` against the day-1, day-3 and day-5
columns with pairs and the tubes ±2 °C (`atoly = 2`) and ±2 °C ±3 h
(`atoly = 2, atolx = 10800`), and plot one pair. Its stated results SHALL
match what the server returns.

#### Scenario: Walkthrough numbers checked
- **WHEN** the test suite runs the walkthrough's calls on the bundled sample
  without network access
- **THEN** the verdicts and the shares of points outside the tube equal the
  numbers printed in the README

#### Scenario: Time tolerance forgives a shifted forecast
- **WHEN** the day-3 pair is compared with ±2 °C and with ±2 °C ±3 h
- **THEN** the share of points outside the tube with ±3 h is not larger than
  without it

### Requirement: Walkthrough caveats

The walkthrough SHALL say that the "actual" column is the latest model run
or analysis and not station measurements, that dates in the future hold
forecasts in both columns, that times are GMT, and that Open-Meteo's free
API is for non-commercial use only and limited to fewer than 10,000 calls a
day.

#### Scenario: Reader learns the limits of the comparison
- **WHEN** a reader reads the walkthrough
- **THEN** it states that the reference column is a model analysis, not
  measured temperature, and that the free API is non-commercial only

### Requirement: Documented live URLs

The walkthrough SHALL give the live Previous Runs API URL that produced the
sample (fixed `start_date` and `end_date`, the pinned model, `format=csv`)
and the raw repository URL of the sample, with the server options needed to
use them (`--allow-network`, or `--allow-host` with the host).

#### Scenario: Same comparison against the API
- **WHEN** a user starts the server with
  `--allow-host previous-runs-api.open-meteo.com` and runs the walkthrough's
  compare call with the documented live URL
- **THEN** the call fetches the URL and compares the same columns as with
  the bundled sample

### Requirement: Example tests run offline

No test run by default or in CI SHALL contact Open-Meteo or any other
internet host. A live check of the documented URL MAY exist only behind an
explicit opt-in environment variable.

#### Scenario: Test suite without internet
- **WHEN** the Python test suite runs on a machine without internet access
- **THEN** every example and fetching test passes or is skipped only because
  the live opt-in is not set
