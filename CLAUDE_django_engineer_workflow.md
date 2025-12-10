
- use conda environment, check the name of the project via the project dir name. if the conda does not exist, 
    create the the conda env, then activate it. if it exist, use it before using python
- for testing, use pytest
- during creating of tests, only create unit tests, focus on mocks, do not require database setup
- setup swagger/openapi and always use serializer. In the serializer, always add openapi description
- in views.py, add openapi comment, add endpoint details
- utilize black python code formatter