.PHONY: build check-secrets clean docs-js docs-python fmt fmt-js fmt-rust help lint lint-js lint-rust \
        test test-docs test-js test-python test-rust

help:  ## Show this help message (all targets, alphabetical)
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

build:  ## Build Rust workspace + maturin develop + pnpm build
	cargo build --workspace
	cargo build -p simtest-funnel-cli --release
	cd crates/simtest-funnel-python && uv run maturin develop --uv
	cd packages/sdk && pnpm run build

check-secrets:  ## Validate .env vars and GitHub Secrets are configured
	@bash scripts/check-secrets.sh

clean:  ## Remove all build artifacts
	cargo clean
	cd packages/sdk && rm -rf dist node_modules src/wasm

docs-python:  ## Generate Python API reference via pdoc
	cd crates/simtest-funnel-python && uv run maturin develop --uv
	uv run pdoc simtest.funnel -o target/doc/python

docs-js:  ## Generate TypeScript API reference via typedoc
	cd packages/sdk && pnpm install && pnpm run build:wasm && pnpm run docs

fmt: fmt-rust fmt-js  ## Auto-format all code

fmt-js:  ## Biome format write (JavaScript/TypeScript)
	cd packages/sdk && pnpm format

fmt-rust:  ## cargo fmt --all
	cargo fmt --all

lint: lint-rust lint-js  ## Run all linters

lint-js:  ## Biome check (JavaScript/TypeScript)
	cd packages/sdk && pnpm lint

lint-rust:  ## Clippy + cargo fmt check
	cargo clippy --workspace --all-targets --features simtest-funnel-core/json -- -D warnings
	cargo fmt --all -- --check

test: test-rust test-python test-js test-docs  ## Run all three language test suites

test-js:  ## vitest (JavaScript/TypeScript)
	cd packages/sdk && pnpm run build:wasm && pnpm test

test-python:  ## pytest tests/python/
	cd crates/simtest-funnel-python && uv run maturin develop --uv
	uv run python -m pytest tests/python/ -v

test-docs:  ## cargo doc --no-deps (excludes FFI crates that trigger rustdoc ICE)
	cargo doc --no-deps --workspace --exclude simtest-funnel-python

test-rust:  ## cargo test --workspace
	cargo test --workspace --features simtest-funnel-core/json
