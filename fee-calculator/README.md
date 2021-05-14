# Monitor + Fee Calculator
A Python CLI tool that can monitor chainsafe proposals + generate fee distribution for chainsafe

## Install
To install, you can run pip inside the root of the repo
```shell script
pip install .
```

For development, you need to use the `--editable` (`-e`) flag
```shell script
pip install -e .
```

(**Note:** Python 3 is required to run this. You may need to use `pip3` instead of `pip` depending on your environment)

## Usage (Fee Calculator)
Before using the module, you must first setup a `config.ini` file in the directory you plan on running the CLI tool. An example config file is provided in this zip file named `config.ini.example`. Fill out the fields as required and save it as `config.ini`

Once you have a `config.ini` in your working directory, you can then run the CLI tool by doing the following

```shell script
avareporter fee-calculator
```

This should generate several files in the current working directory as well print out a JSON to STDOUT (these settings can be changed inside `config.ini`)

## Usage (Monitor)
Before using the module, you must first setup a `config.ini` file in the directory you plan on running the CLI tool. An example config file is provided in this repo named `config.ini.monitor.example`. Fill out the fields as required and save it as `config.ini`

You must also configure a logging configuration file as `logging.conf`. This is a standard python logging configuration file.

Once you have a `config.ini` in your working directory, you can then run the CLI tool by doing the following

```shell script
avareporter monitor
```

This will run forever, logging alerts as they are found. 
