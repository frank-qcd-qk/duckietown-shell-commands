import argparse
import datetime
import os
import sys

from dt_shell import DTCommandAbs, dtslogger
from dt_shell.env_checks import get_dockerhub_username
from dt_shell.remote import dtserver_update_challenge
from duckietown_challenges.local_config import read_challenge_info


class DTCommand(DTCommandAbs):

    @staticmethod
    def command(shell, args):
        token = shell.get_dt1_token()

        parser = argparse.ArgumentParser()
        parser.add_argument('--no-cache', default=False, dest='no_cache', action='store_true')
        parser.add_argument('--no-push', default=False, dest='no_push', action='store_true')
        parsed = parser.parse_args(args)

        username = get_dockerhub_username(shell)
        ci = read_challenge_info('.')
        challenge_name = ci.challenge_name

        import docker

        date_tag = tag_from_date(datetime.datetime.now())
        repository = '%s/%s-evaluator' % (username, challenge_name)
        tag = '%s:%s' % (repository, date_tag)

        df = 'Dockerfile'
        if not os.path.exists(df):
            msg = 'I expected to find the file "%s".' % df
            raise Exception(msg)

        client = docker.from_env()
        dtslogger.info('Building image...')
        image, logs = client.images.build(path='.', tag=tag, nocache=parsed.no_cache)
        dtslogger.info('...done.')
        sha = image.id  # sha256:XXX
        complete = '%s@%s' % (tag, sha)

        # complete = '%s@%s' % (repository, sha)

        dtslogger.info('The complete image is %s' % complete)

        if not parsed.no_push:
            dtslogger.info('Pushing image...')
            for line in client.images.push(repository=repository, tag=date_tag, stream=True):  # , tag=tag)

                line = line.replace('\n', ' ')
                sys.stderr.write('docker: ' + str(line).strip()[:80] + ' ' + '\r')

            dtslogger.info('...done')

        challenge_parameters = {
            'protocol': 'p1',
            # 'container': complete,
            'container': tag,
        }
        dtserver_update_challenge(token, challenge_name, challenge_parameters)


def tag_from_date(d):
    # YYYY-MM-DDTHH:MM:SS[.mmmmmm][+HH:MM].
    s = d.isoformat()

    s = s.replace(':', '_')
    s = s.replace('T', '_')
    s = s.replace('-', '_')
    s = s[:s.index('.')]
    return s