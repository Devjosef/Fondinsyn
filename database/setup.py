from setuptools import setup, find_packages

setup(
    name='portfolio_etl',
    version='0.1.0',
    description='ETL pipeline for Swedish index fund holdings',
    author='Devjosef',
    author_email='Devjosef1@gmail.com',
    url='https://github.com/Devjosef/index-funds-etl',
    license='MIT',

    packages=find_packages(where='src'),
    package_dir={'': 'src'},

    include_package_data=True,
    zip_safe=False,

    install_requires=[
        'sqlalchemy>=1.4',
        'psycopg2-binary>=2.9',
        'alembic>=1.13',
        'pydantic>=2.5',
    ],

    extras_require={
        'dev': [
            'pytest>=7.0',
            'pytest-cov',
            'black',
            'ruff',
            'mypy',
            'pre-commit',
        ],
        'postgres': ['psycopg2-binary'],
    },

    entry_points={
        'console_scripts': [
            # configure if CLI is added later
            # 'etl=portfolio_etl.cli:main',
        ]
    },

    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: Financial and Insurance Industry',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Office/Business :: Financial :: Investment',
    ],
)
