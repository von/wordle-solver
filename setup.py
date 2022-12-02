#!/usr/bin/env python
# encoding: utf-8

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(name='wordle-solver',
      version='0.1',
      description="Tools for solving Wordle",
      author="Von Welch",
      author_email="von@vwelch.com",
      packages=['WordleSolver'],
      entry_points={
          'console_scripts': [
              'wordle = WordleSolver.wordle:main'
          ]
      },
      install_requires=['wordfreq'],
      package_data={"WordleSolver": ["non_words.txt"]}
      )
