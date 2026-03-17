"""setuptools configuration for keyforge-git-hooks."""

from setuptools import setup, find_packages

setup(
    name="keyforge-git-hooks",
    version="0.1.0",
    description="KeyForge pre-commit hook — scan staged files for hardcoded secrets",
    long_description=open("README.md", encoding="utf-8").read() if __import__("os").path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    author="KeyForge Team",
    author_email="team@keyforge.dev",
    url="https://github.com/keyforge/keyforge-git-hooks",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "keyforge-scan=keyforge_hooks.cli:cli_entry",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Security",
        "Topic :: Software Development :: Quality Assurance",
    ],
    keywords="security secrets pre-commit git hooks scanning",
)
