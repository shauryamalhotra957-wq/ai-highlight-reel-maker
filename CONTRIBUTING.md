# Contributing

Set up the project with development dependencies:

~~~bash
python -m pip install -e ".[dev]"
pytest
~~~

Use demo mode for deterministic tests. Changes to clip selection, timestamp handling, FFmpeg invocation, upload limits, or rendered EDLs should include focused tests.

Treat uploaded media and filenames as untrusted. Do not commit source footage, rendered clips, credentials, or generated job directories.
