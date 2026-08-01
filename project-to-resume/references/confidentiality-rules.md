# Confidentiality Rules

## Default Redactions

Do not expose or copy:

- company, customer, vendor, department, or individual names unless the user says they are public
- repository folder names, internal product names, codenames, and project titles unless public status is confirmed
- internal domains, hostnames, IP addresses, ports tied to private systems, repository URLs, ticket URLs, or cloud account identifiers
- credentials, tokens, cookies, passwords, API keys, connection strings, `.env` contents, certificates, or private keys
- private datasets, source documents, prompt contents, logs, user records, or proprietary business rules
- unpublished model names, pricing, contract terms, incident details, or security topology

Replace sensitive identities with stable neutral terms such as “某制造企业”, “内部知识库”, “企业文档”, or “受限网络环境” only when the abstraction remains truthful.

## Safe Inspection

- Inspect names and metadata before file contents.
- Never read `.env`, credential stores, key material, cookies, database files, model weights, raw production logs, or private data exports.
- Do not print environment variables.
- Do not access external issue trackers, deployment consoles, services, or networks unless the user explicitly authorizes it and it is necessary.
- Treat Git remote URLs, author emails, and commit messages as potentially sensitive. Do not copy emails into artifacts.

## Claim Review

For every ledger claim set confidentiality risk:

- `NONE`: public or generic technical fact
- `LOW`: internal names can be safely generalized
- `MEDIUM`: architecture, usage, or metrics may expose protected context
- `HIGH`: secrets, customer data, security details, private datasets, or contractual information
- `USER_CONFIRMATION_REQUIRED`: public status is unknown

`HIGH` claims are not resume eligible. `MEDIUM` and `USER_CONFIRMATION_REQUIRED` claims require sanitized wording or explicit confirmation.

Repository presence does not make its name public. Before confirmation, derive a neutral title from verified function, such as “工程图 PDF 质量检验平台”, and normalize absolute roots to `<REPOSITORY_ROOT>` in persisted artifacts.

Run a final search for secret-like values and private identifiers before delivery. A clean scan does not prove public disclosure is authorized; apply judgment.
