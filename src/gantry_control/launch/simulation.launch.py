from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import xacro


def launch_setup(context):
    description = Path(get_package_share_directory('gantry_description'))
    gz = Path(get_package_share_directory('ros_gz_sim'))
    vision = context.launch_configurations.get('vision', 'false').lower() == 'true'
    robot = xacro.process_file(str(description / 'urdf/gantry.urdf.xacro'),
                              mappings={'controllers': str(description / 'config/controllers.yaml')}).toxml()
    world = description / ('worlds/lab_vision.sdf' if vision else 'worlds/lab.sdf')
    # The camera needs headless rendering; the plain world keeps the original server-only mode.
    gz_flags = '-r -s --headless-rendering' if vision else '-r -s'
    bridge = ['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock']
    if vision:
        bridge.append('/overhead/image@sensor_msgs/msg/Image[gz.msgs.Image')
    return [
        IncludeLaunchDescription(PythonLaunchDescriptionSource(str(gz / 'launch/gz_sim.launch.py')),
                                 launch_arguments={'gz_args': f'{gz_flags} {world}'}.items()),
        Node(package='robot_state_publisher', executable='robot_state_publisher',
             parameters=[{'robot_description': robot, 'use_sim_time': True}]),
        Node(package='ros_gz_sim', executable='create',
             arguments=['-topic', 'robot_description', '-name', 'gantry']),
        Node(package='ros_gz_bridge', executable='parameter_bridge', arguments=bridge),
        Node(package='controller_manager', executable='spawner',
             arguments=['joint_state_broadcaster', 'gantry_controller', '--controller-manager-timeout', '90']),
        Node(package='gantry_monitor', executable='trajectory_safety_monitor', output='screen'),
        Node(package='gantry_control', executable='protocol_server',
             parameters=[{'log_dir': LaunchConfiguration('log_dir')}], output='screen'),
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('log_dir', default_value='/tmp/gantry-logs'),
        DeclareLaunchArgument('vision', default_value='false',
                              description='true: add the overhead camera world and publish /overhead/image'),
        OpaqueFunction(function=launch_setup),
    ])
