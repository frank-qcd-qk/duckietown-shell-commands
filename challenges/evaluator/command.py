import argparse
import os
import socket
import sys
import time

from dt_shell import dtslogger, DTCommandAbs
from dt_shell.env_checks import check_docker_environment
from dt_shell.remote import get_duckietown_server_url

usage = """

## Basic usage

    Run the evaluator continuously:
    
        $ dts challenges evaluator
    
    This will evaluate your submissions preferentially, or others if yours are not available.
    
    
    Run the evaluator on a specific submission:
    
        $ dts challenges evaluator --submission ID
        
    This evaluates a specific submission.
    
    
    
    To re-evaluate after the first time, use --reset:
    
        $ dts challenges evaluator --submission ID --reset


## Advanced usage

    Pretend that you have a GPU:
    
        $ dts challenges evaluator --features 'gpu: 1'
        
    Use '--name' to distinguish multiple evaluators on the same machine.
    Otherwise the name is autogenerated.
    
        $ dts challenges evaluator --name Instance1 &
        $ dts challenges evaluator --name Instance2 &
        

"""


class DTCommand(DTCommandAbs):

    @staticmethod
    def command(shell, args):
        check_docker_environment()

        home = os.path.expanduser('~')
        prog = 'dts challenges evaluator'
        parser = argparse.ArgumentParser(prog=prog, usage=usage)

        group = parser.add_argument_group('Basic')

        group.add_argument('--submission', type=int, default=None,
                           help='Run a specific submission.')
        group.add_argument('--reset', dest='reset', action='store_true', default=False,
                           help='(needs --submission) Re-evaluate the specific submission.')

        group = parser.add_argument_group('Advanced')

        group.add_argument('--no-watchtower', dest='no_watchtower', action='store_true', default=False,
                           help="Disable starting of watchtower")
        group.add_argument('--no-pull', dest='no_pull', action='store_true', default=False,
                           help="Disable pulling of container")
        group.add_argument('--image', help="Evaluator image to run", default='duckietown/dt-challenges-evaluator:v3')

        group.add_argument('--name', default=None, help='Name for this evaluator')
        group.add_argument("--features", default=None, help="Pretend to be what you are not.")

        parsed = parser.parse_args(args)

        machine_id = socket.gethostname()

        if parsed.name is None:
            container_name = '%s-%s' % (socket.gethostname(), os.getpid())
        else:
            container_name = parsed.name

        import docker
        client = docker.from_env()

        command = []

        if parsed.submission:
            command += ['--submission', str(parsed.submission)]

            if parsed.reset:
                command += ['--reset']
        else:
            command += ['--continuous']

        command += ['--name', container_name]
        command += ['--machine-id', machine_id]
        if parsed.features:
            dtslogger.debug('Passing features %r' % parsed.features)
            command += ['--features', parsed.features]

        volumes = {
            '/var/run/docker.sock': {'bind': '/var/run/docker.sock', 'mode': 'rw'},
            os.path.join(home, '.dt-shell'): {'bind': '/root/.dt-shell', 'mode': 'ro'},
            '/tmp': {'bind': '/tmp', 'mode': 'rw'}
        }
        env = {}

        if not parsed.no_watchtower:
            ensure_watchtower_active(client)

        h = socket.gethostname()
        env['DTSERVER'] = get_duckietown_server_url().replace("localhost", h + '.local')

        image = parsed.image
        name, tag = image.split(':')
        if not parsed.no_pull:
            dtslogger.info('Updating container %s' % image)

            client.images.pull(name, tag)

        try:
            container = client.containers.get(container_name)
        except:
            pass
        else:
            dtslogger.error('stopping previous %s' % container_name)
            container.stop()
            dtslogger.error('removing')
            container.remove()

        dtslogger.info('Starting container %s with %s' % (container_name, image))

        dtslogger.info('Container command: %s' % " ".join(command))
        
        client.containers.run(image,
                              command=command,
                              volumes=volumes,
                              environment=env,
                              network_mode='host',
                              detach=True,
                              name=container_name,
                              tty=True)
        while True:
            try:
                container = client.containers.get(container_name)
            except Exception as e:
                msg = 'Cannot get container %s: %s' % (container_name, e)
                dtslogger.error(msg)
                dtslogger.info('Will wait.')
                time.sleep(5)
                continue

            dtslogger.info('status: %s' % container.status)
            if container.status == 'exited':

                msg = 'The container exited.'

                logs = ''
                for c in container.logs(stdout=True, stderr=True, stream=True):
                    logs += c
                dtslogger.error(msg)

                tf = 'evaluator.log'
                with open(tf, 'w') as f:
                    f.write(logs)

                msg = 'Logs saved at %s' % (tf)
                dtslogger.info(msg)

                break

            try:
                for c in container.logs(stdout=True, stderr=True, stream=True, follow=True):
                    sys.stdout.write(c)

                time.sleep(3)
            except Exception as e:
                dtslogger.error(e)
                dtslogger.info('Will try to re-attach to container.')
                time.sleep(3)
            except KeyboardInterrupt:
                dtslogger.info('Received CTRL-C. Stopping container...')
                container.stop()
                dtslogger.info('Removing container')
                container.remove()
                dtslogger.info('Container removed.')
                break


def ensure_watchtower_active(client):
    containers = client.containers.list(filters=dict(status='running'))
    watchtower_tag = 'v2tec/watchtower'
    found = None
    for c in containers:
        tags = c.image.attrs['RepoTags']
        for t in tags:
            if watchtower_tag in t:
                found = c

    if found is not None:
        print('I found watchtower active.')
    else:
        print('Starting watchtower')
        env = {}
        volumes = {
            '/var/run/docker.sock': {'bind': '/var/run/docker.sock', 'mode': 'rw'},
            # os.path.join(home, '.dt-shell'): {'bind': '/root/.dt-shell', 'mode': 'ro'}
        }
        container = client.containers.run(watchtower_tag, volumes=volumes, environment=env, network_mode='host',
                                          detach=True)
        print('Detached: %s' % container)


def indent(s, prefix, first=None):
    s = str(s)
    assert isinstance(prefix, str)
    lines = s.split('\n')
    if not lines:
        return ''

    if first is None:
        first = prefix

    m = max(len(prefix), len(first))

    prefix = ' ' * (m - len(prefix)) + prefix
    first = ' ' * (m - len(first)) + first

    # differnet first prefix
    res = ['%s%s' % (prefix, line.rstrip()) for line in lines]
    res[0] = '%s%s' % (first, lines[0].rstrip())
    return '\n'.join(res)
