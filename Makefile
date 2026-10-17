# Makefile for local dev, production build and deploy
# Usage examples:
#  make serve
#  make build                        # uses default PROD_BASEURL if not overridden
#  PROD_BASEURL="https://www.ehu.eus/chemistry/theory/" make build
#  make deploy                       # incremental deploy (only changed files)
#  make deploy-full                  # full deploy (overwrite everything)
#
# You can create a local .env file with the following variables (DO NOT COMMIT .env):
# PROD_BASEURL="https://www.ehu.eus/chemistry/theory/"
# SFTP_USER=scwtcg
# SFTP_HOST=alweb.ehu.eus
# REMOTE_PATH=/users/scwtcg/public_html

# Load optional .env (if present) so users can keep credentials out of the shell.
-include .env

.PHONY: serve build validate-data validate check-public-links deploy deploy-full clean

# Defaults (override via environment, .env, or on the make command line)
PROD_BASEURL ?= https://www.ehu.eus/chemistry/theory/
SFTP_USER    ?= scwtcg
SFTP_HOST    ?= alweb.ehu.eus
REMOTE_PATH  ?= /users/scwtcg/public_html

serve:
	hugo server -D -F --bind 127.0.0.1 --port 1313 --baseURL http://127.0.0.1:1313/

build:
	echo "Building with baseURL: $(PROD_BASEURL)"
	hugo -D --minify --cleanDestinationDir --baseURL "$(PROD_BASEURL)"

validate-data:
	python3 scripts/validate_site_data.py

validate: validate-data build check-public-links

check-public-links:
	@test -d public || (echo "Run 'make build' before deploying" >&2 && exit 1)
	@if find public -type f -name '*.html' -exec grep -nHE 'https?://(localhost|127\.0\.0\.1)(:[0-9]+)?([/\"?#]|$$)' {} +; then \
		echo "Refusing to deploy: generated HTML contains localhost links. Run 'make build' first." >&2; \
		exit 1; \
	fi

# Incremental deploy using lftp mirror --only-newer.
# Only uploads files that are newer than the remote copy.
# Requires a working SSH key for $(SFTP_USER)@$(SFTP_HOST).
deploy: check-public-links
	@test -n "$(SFTP_USER)" || (echo "Set SFTP_USER" && exit 1)
	@test -n "$(SFTP_HOST)" || (echo "Set SFTP_HOST" && exit 1)
	@test -n "$(REMOTE_PATH)" || (echo "Set REMOTE_PATH" && exit 1)
	@echo "Incremental deploy to $(SFTP_USER)@$(SFTP_HOST):$(REMOTE_PATH) ..."
	lftp sftp://$(SFTP_USER)@$(SFTP_HOST) \
		-e "set sftp:auto-confirm yes; set net:max-retries 2; mirror -R --only-newer --verbose public/ $(REMOTE_PATH); bye"

# Full deploy using lftp mirror.
# Overwrites the remote directory completely (use for first deploy or full reset).
deploy-full: check-public-links
	@test -n "$(SFTP_USER)" || (echo "Set SFTP_USER" && exit 1)
	@test -n "$(SFTP_HOST)" || (echo "Set SFTP_HOST" && exit 1)
	@test -n "$(REMOTE_PATH)" || (echo "Set REMOTE_PATH" && exit 1)
	@echo "Full deploy to $(SFTP_USER)@$(SFTP_HOST):$(REMOTE_PATH) ..."
	lftp sftp://$(SFTP_USER)@$(SFTP_HOST) \
		-e "set sftp:auto-confirm yes; set net:max-retries 2; mirror -R --delete --verbose public/ $(REMOTE_PATH); bye"

clean:
	rm -rf public/
