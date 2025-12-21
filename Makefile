.PHONY: serve build clean draft

# Run local dev server and clean on exit
serve:
	hugo server -D --bind 0.0.0.0 && make clean

# Build for production
build:
	hugo --minify

# Clean build artifacts
clean:
	rm -rf public/ resources/
