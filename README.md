## :gear: cbconf - Configuration Management

cbconf is a configuration management library for Python based on [pydantic](https://pydantic-docs.helpmanual.io/)

It easily allows you to

* load your configuration from config files, environment variables (and any other source!)
* transform the loaded data into a desired format and validate it
* access the results as Python dataclass-like objects with full IDE support

It furthermore supports you in common use cases like:

* Multiple environments, each with a unique configuration
* Singleton with lazy loading
* Custom config sources (`vault`, `consul`, etc)


## :rocket: Quick Start
```python
from cbconf import Settings, Field

class Environment(Settings, sources=["env"]):
    ci_commit_sha: Optional[str] = Field(default=None)
    current_branch: Optional[str] = Field(default=None)
    debug: bool = Field(default=False)
    health_check_port: int = Field(default=8000)
    health_check_timeout: float = Field(default=2.0)
    service_name: Optional[str] = Field(default=None, env="SVC_NAME")
    unit_test_mode: bool = Field(default=False)
    grpc_port: int = Field(default=50051)


class AwsConfig(Settings, sources=("env",)):
    aws_access_key_id: Optional[str] = Field(default=None)
    aws_secret_access_key: Optional[str] = Field(default=None)

    class LocalConfig:
        ini_file = os.getenv("AWS_SHARED_CREDENTIALS_FILE", "~/.aws/credentials")
```

It's really easy to set up job or service configs using the `cbconsul` package.
```python
from cbconf import Settings, Field
from cbconf import registry as reg
from cbconsul import ConsulSource


# this is handled automatically in service bootstrap, just here for illustration
consul_source = reg.register(ConsulSource, "consul")
consul_source.configure(consul_address="http://localhost:8500")
consul_source.configure("dev", consul_address="http://consul-dev.example.com")
consul_source.configure("stg", consul_address="http://consul-stg.example.com")
consul_source.configure("prd", consul_address="http://consul-prd.example.com")


class JobSettings(Settings, consul_path="example-job/config", sources=("env", "consul")):
    service_name: str = Field(default="example-job", env="SVC_NAME")
    aws_region: str = Field(default=...)
    batch_size: int = Field(default=...)
    db_main_hostname: str = Field(default=...)
    db_main_port: int = Field(default=...)
    db_main_vault_path: str = Field(default=...)
    db_vault_mount_point: str = Field(default=...)
    num_batches: int = 1
    num_workers: int = 1
    s3_bucket: str = Field(default=...)
```

From now on, in any other file, you can access your config directly:

```python
from config import JobSettings, Environment

print(Environment().service_name) # will print whatever's in SVC_NAME env var
assert Environment() is Environment() # True
```

The config does not have to be loaded explicitly, nor instantiated globally, it's automatically
built from configured sources the first time you access it.

### Multiple Environments

`cbconf` defaults to pulling environment from `SERVER_ENV`, but this is configurable too with the `server_env` setting:

```python
from cbconf import Settings

class MyConfig(Settings):
    class Config:
        server_env = os.getenv("CURRENT_ENV")

# alternate syntax
class MyConfig(Settings, server_env=os.getenv("CURRENT_ENV")):
    ...
```

`server_env` can be either a string, or a callable that returns a string.

The `server_env` affects many things. If it's set, your `EnvSource` will automatically be configured to pull environment variables from `.env.{server_env}`. This can also be done manually.

```python
def get_server_env() -> str:
    return "local"

class MyConfig(Settings, server_env=get_server_env):
    class LocalConfig: # if `local`
        env_file = ".env.local"
        consul_address = "http://localhost:8500"

    class DevConfig: # if `dev`
        env_file = ".env.dev"
        consul_address = "http://consul-dev.example.com"

    class TestConfig: # if `test`
        env_file = ".env.test"
```
Alternate configuration:
```python
from cbconf import registry

registry.configure("env", "dev", env_file=".env.dev")
registry.configure("consul", "prd", consul_address="http://consul-prd.example.com")

```

## Explicit Loading
In some scenarios, the config should not be a global singleton, but loaded explicitly and passed around locally.

```python
class MyConfig(Settings, singleton=False):
    ...
```
or alternatively
```python
class MyConfig(Settings):
    class Config:
        singleton = False
```
