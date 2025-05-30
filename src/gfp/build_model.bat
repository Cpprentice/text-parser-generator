@echo off

pushd %~dp0

linkml generate json-schema .\config_schema.yaml > jsonschema.json
datamodel-codegen --input jsonschema.json --output model3.py --output-model-type pydantic_v2.BaseModel --field-constraints

popd
