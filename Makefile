.PHONY: build build-sdk check-secrets clean demo demo-serve docs-js docs-python fmt fmt-js fmt-rust help lint lint-js lint-rust \
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

build-sdk:  ## Build the @simtest-js/funnel SDK (wasm glue + dist)
	cd packages/sdk && pnpm install && pnpm build

demo: build-sdk  ## Build the browser demo into target/doc/demo/
	cd examples/web && pnpm install && pnpm build
	mkdir -p target/doc/demo
	cp -r examples/web/dist/. target/doc/demo/
	# Cloudflare Pages honors a single _headers file at the deploy root, so
	# the wasm MIME rule must live at target/doc/_headers (not under demo/).
	printf '/*.wasm\n  Content-Type: application/wasm\n' > target/doc/_headers

demo-serve: build-sdk  ## Run the demo dev server (Vite) for local preview
	cd examples/web && pnpm install && pnpm dev

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
	cd examples/web && pnpm lint

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
