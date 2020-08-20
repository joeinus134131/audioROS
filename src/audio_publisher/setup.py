from setuptools import setup

package_name = 'audio_publisher'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='duembgen',
    maintainer_email='frederike.duembgen@epfl.ch',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'file = audio_publisher.file_publisher:main',
            'stream = audio_publisher.stream_publisher:main'
        ],
    },
)