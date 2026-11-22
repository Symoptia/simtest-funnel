.PHONY: browser-setup build build-sdk check-secrets clean demo demo-serve docs-js docs-python fmt fmt-js fmt-rust help lint lint-js lint-python lint-rust \
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

# Headless browser for driving the demo (not needed for build, test or lint).
# The devcontainer image has the shared libraries; the browser is downloaded
# here on demand so the image stays small.
BROWSER_DIR ?= $(HOME)/.cache/simtest-funnel-browser
PLAYWRIGHT_VERSION ?= 1.56.1

browser-setup:  ## Install a headless Chromium on demand (~350 MB in ~/.cache) for driving the demo in a browser
	mkdir -p $(BROWSER_DIR)
	cd $(BROWSER_DIR) && { [ -f package.json ] || npm init -y >/dev/null; } && \
		npm install --no-fund --no-audit playwright@$(PLAYWRIGHT_VERSION) && \
		PLAYWRIGHT_BROWSERS_PATH=$(BROWSER_DIR)/browsers npx playwright install chromium-headless-shell
	@echo "Browser ready. In the directory of a Playwright script:"
	@echo "  ln -sfn $(BROWSER_DIR)/node_modules node_modules"
	@echo "  PLAYWRIGHT_BROWSERS_PATH=$(BROWSER_DIR)/browsers node script.mjs"

build-sdk:  ## Build the @simtest-js/funnel SDK (wasm glue + dist)
	cd packages/sdk && pnpm install && pnpm build

demo: build-sdk  ## Build the browser demo into target/doc/demo/ (VITE_WEATHER_LIVE=false: sample-only weather tab)
	cd examples/web && pnpm install && VITE_WEATHER_LIVE=$(VITE_WEATHER_LIVE) pnpm build
	rm -rf target/doc/demo
	mkdir -p target/doc/demo
	cp -r examples/web/dist/. target/doc/demo/
	# Cloudflare Pages honors a single _headers file at the deploy root, so
	# the wasm MIME rule and the demo's connect-src policy (only the site and,
	# with live weather data, the two Open-Meteo API hosts) must live at
	# target/doc/_headers (not under demo/).
	VITE_WEATHER_LIVE=$(VITE_WEATHER_LIVE) node examples/web/scripts/headers.mjs target/doc/_headers

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

lint: lint-rust lint-js lint-python  ## Run all linters

lint-js:  ## Biome check (JavaScript/TypeScript)
	cd packages/sdk && pnpm lint
	cd examples/web && pnpm lint

lint-python:  ## mypy --strict (simtest-funnel-mcp package and its tests)
	uv run mypy python/simtest-funnel-mcp/src python/simtest-funnel-mcp/tests

lint-rust:  ## Clippy + cargo fmt check
	cargo clippy --workspace --all-targets --features simtest-funnel-core/json -- -D warnings
	cargo fmt --all -- --check

test: test-rust test-python test-js test-docs  ## Run all three language test suites

test-js:  ## vitest (JavaScript/TypeScript): SDK, then the browser demo
	cd packages/sdk && pnpm run build:wasm && pnpm test
	cd examples/web && pnpm install && pnpm test

test-python:  ## pytest tests/python/ + simtest-funnel-mcp tests
	cd crates/simtest-funnel-python && uv run maturin develop --uv
	uv run python -m pytest tests/python/ python/simtest-funnel-mcp/tests -v

test-docs:  ## cargo doc --no-deps (excludes FFI crates that trigger rustdoc ICE)
	cargo doc --no-deps --workspace --exclude simtest-funnel-python

test-rust:  ## cargo test --workspace
	cargo test --workspace --features simtest-funnel-core/json
