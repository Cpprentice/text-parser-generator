@echo off

pushd %~dp0

linkml generate json-schema .\parser-schema-specification.yaml > parser-schema-specification.schema.json
datamodel-codegen --input parser-schema-specification.schema.json --input-file-type jsonschema --output model.py --output-model-type pydantic_v2.BaseModel --field-constraints

popd
