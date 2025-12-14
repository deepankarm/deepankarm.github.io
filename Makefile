.PHONY: serve build clean draft

# Run local dev server
serve:
	hugo server -D --bind 0.0.0.0

# Build for production
build:
	hugo --minify

# Clean build artifacts
clean:
	rm -rf public/ resources/
