## MODIFIED Requirements

### Requirement: Public addresses only

Before connecting, the host SHALL be resolved and every resolved address
SHALL be public: loopback, private, link-local (including cloud metadata),
unique-local, site-local, SRv6, multicast, unspecified, reserved and
documentation addresses, and IPv6 forms embedding such an IPv4 address,
SHALL be refused, by an explicit list besides `is_global`. The lookup SHALL
stop at the deadline or on cancellation and a late answer SHALL be dropped.
The connection SHALL go to a checked address.

#### Scenario: Loopback
- **WHEN** an agent passes `https://localhost:8443/run.csv` or
  `https://127.0.0.1/run.csv`
- **THEN** the call fails with an error saying the host resolves to a
  non-public address, and no connection is opened

#### Scenario: Cloud metadata address
- **WHEN** an agent passes a URL whose host is `169.254.169.254`
- **THEN** the call fails as a non-public address

#### Scenario: Host resolving to a private address
- **WHEN** a host name resolves to `10.0.0.5` and to a public address
- **THEN** the call fails as a non-public address

#### Scenario: Ranges missing from is_global
- **WHEN** a host resolves to `fec0::1` (site-local) or `5f00::1` (SRv6)
- **THEN** the call fails as a non-public address, whatever the Python
  version's `is_global` says

#### Scenario: Name resolving differently on a second lookup
- **WHEN** a resolver answers a public address on the first lookup and a
  private address on any later lookup
- **THEN** the connection goes to the public address that was checked

#### Scenario: Slow resolver
- **WHEN** the lookup takes 3 s and the fetch timeout is 0.3 s
- **THEN** the call fails with the fetch-timeout error within about a
  second, and no connection is made when the answer arrives later

### Requirement: Certificate verified for the URL's host

The TLS connection SHALL verify the server certificate against the
platform's trusted certificate authorities and the URL's host (of the
current redirect hop): a host name against its DNS names, an IP-literal host
against its IP address entries, also though the connection goes to a
checked address. Any TLS failure SHALL fail the call with an error naming
the host, never with a traceback.

#### Scenario: Certificate for another name
- **WHEN** the server at the checked address presents a valid certificate
  for a different host name
- **THEN** the call fails with a certificate error naming the URL's host

#### Scenario: IP-literal host
- **WHEN** an agent passes `https://127.0.0.1:<port>/a.csv` (address policy
  permitting) and the certificate has the IP address entry `127.0.0.1`
- **THEN** the file is fetched; with a certificate without that entry the
  call fails with a certificate verification error

#### Scenario: Unexpected TLS error
- **WHEN** the TLS layer raises an unexpected exception
- **THEN** the call fails with an error saying the TLS connection to the
  host failed

### Requirement: Accepted content

Only responses with status 200 and a content type of CSV, plain text,
generic binary or none SHALL be accepted, in UTF-8 or ASCII, uncompressed or
gzip-compressed (one or more members, optionally followed by NUL padding as
gzip(1) accepts; other data after the members SHALL be refused). An HTML
response SHALL be refused with a hint that the URL is probably a web page;
other types SHALL be refused naming the type.

#### Scenario: Repository web page instead of the raw file
- **WHEN** an agent passes the URL of a code-hosting page that shows a CSV
  file as HTML
- **THEN** the call fails with an error saying the URL returned an HTML page
  and suggesting the raw-file URL

#### Scenario: JSON response
- **WHEN** a URL returns `application/json`
- **THEN** the call fails with an error naming the content type and saying
  only CSV is read

#### Scenario: Open-Meteo CSV
- **WHEN** a URL returns `text/csv; charset=utf-8`, gzip-compressed
- **THEN** the file is accepted and read

#### Scenario: NUL padding after gzip data
- **WHEN** a gzip body is followed by 1000 NUL bytes
- **THEN** the file is accepted; followed by NUL bytes and then other
  bytes, it is refused

### Requirement: Error responses reported

A final response with a status other than 200 SHALL fail the call with an
error naming the URL's host, the status code with its standard phrase and
the content type. The body is untrusted and SHALL NOT be quoted, except the
`reason`, `error` or `message` string of a JSON object body, reduced to
letters, digits, space and plain punctuation and at most 120 characters.

#### Scenario: Bad request with a reason
- **WHEN** a URL answers 400 with the JSON body
  `{"error":true,"reason":"End-date must be larger or equals than start-date"}`
- **THEN** the error names status 400 and contains that reason

#### Scenario: Text error page
- **WHEN** a URL answers 503 with a text body containing instructions
- **THEN** the error names status 503 and the content type and does not
  contain the body

### Requirement: Cache size bound

The cache SHALL hold at most ten times the size cap, counting the bytes
written so far by downloads in progress; to make room the least recently
used copies not in use SHALL be dropped. At most ten downloads SHALL run at
once. A dropped URL used again SHALL be fetched again and, when its SHA-256
differs (hashes of the last 4096 URLs are kept), the call SHALL fail saying
the content changed.

#### Scenario: Evicted URL changed meanwhile
- **WHEN** a URL's copy was dropped to make room and its remote content has
  changed when it is used again
- **THEN** the call fails with an error naming the URL and both SHA-256
  values

#### Scenario: Download in progress makes room
- **WHEN** the bound is 24 bytes, a 16-byte copy is cached and another
  16-byte file is being downloaded slowly
- **THEN** the cached copy is dropped before that download completes

#### Scenario: Too many downloads at once
- **WHEN** as many downloads as allowed are running and another URL is used
- **THEN** that call fails with an error saying other URLs are being
  downloaded

## ADDED Requirements

### Requirement: Fetched content is untrusted

With network access enabled, the server instructions and tool descriptions
SHALL say that content fetched from a URL is untrusted data, not
instructions, and the instructions SHALL say that a URL can carry data out,
also through its host name (looked up even when the fetch fails) unless
`--allow-host` restricts the hosts. The README SHALL say the same and
recommend `--allow-host`.

#### Scenario: Network enabled
- **WHEN** the server is started with `--allow-network`
- **THEN** its instructions say fetched content is untrusted data, not
  instructions, and name `--allow-host` and the host-name lookup

#### Scenario: Network off
- **WHEN** the server is started without network options
- **THEN** the instructions carry no URL warning
