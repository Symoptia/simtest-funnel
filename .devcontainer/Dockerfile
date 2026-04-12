FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

COPY install-system-deps.sh /tmp/devcontainer/
RUN bash /tmp/devcontainer/install-system-deps.sh && rm -rf /tmp/devcontainer

# Rust stable (via rustup) — installed globally so all users (including vscode) can access
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH="/usr/local/cargo/bin:${PATH}"

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain stable --profile minimal && \
    rustup component add clippy rustfmt && \
    rustup target add wasm32-unknown-unknown && \
    chmod -R a+rw $RUSTUP_HOME $CARGO_HOME

# Node.js 22 LTS
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs

# pnpm 9
RUN npm install -g pnpm@9

# wasm-pack (latest stable) — installs into CARGO_HOME/bin which is on PATH
RUN curl https://rustwasm.github.io/wasm-pack/installer/init.sh -sSf | sh

# lefthook (from official Cloudsmith repo)
RUN curl -1sLf 'https://dl.cloudsmith.io/public/evilmartians/lefthook/setup.deb.sh' \
    | bash && apt-get install -y lefthook

# wrangler (Cloudflare CLI, for Pages deploy and IAC)
RUN npm install -g wrangler@latest

