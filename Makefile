.PHONY: build check-secrets clean fmt fmt-js fmt-rust help lint lint-js lint-rust \
        test test-js test-python test-rust

help:  ## Show this help message (all targets, alphabetical)
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

build:  ## Build Rust workspace + maturin develop + pnpm build
	cargo build --workspace
	cd crates/simtest-funnel-python && python -m maturin develop --uv
	cd packages/sdk && pnpm run build

check-secrets:  ## Validate .env vars and GitHub Secrets are configured
	@bash scripts/check-secrets.sh

clean:  ## Remove all build artifacts
	cargo clean
	cd packages/sdk && rm -rf dist node_modules src/wasm

fmt: fmt-rust fmt-js  ## Auto-format all code

fmt-js:  ## Biome format write (JavaScript/TypeScript)
	cd packages/sdk && pnpm format

fmt-rust:  ## cargo fmt --all
	cargo fmt --all

lint: lint-rust lint-js  ## Run all linters

lint-js:  ## Biome check (JavaScript/TypeScript)
	cd packages/sdk && pnpm lint

lint-rust:  ## Clippy + cargo fmt check
	cargo clippy --workspace -- -D warnings
	cargo fmt --all -- --check

test: test-rust test-python test-js  ## Run all three language test suites

test-js:  ## vitest (JavaScript/TypeScript)
	cd packages/sdk && pnpm run build:wasm && pnpm test

test-python:  ## pytest tests/python/
	cd crates/simtest-funnel-python && python -m maturin develop --uv
	uv run python -m pytest tests/python/ -v

test-rust:  ## cargo test --workspace
	cargo test --workspace
