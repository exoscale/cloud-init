import time

from cloudinit import ec2_utils as ec2
from cloudinit import log as logging
from cloudinit import sources
from cloudinit import url_helper

API_VERSION = "latest"
LOG = logging.getLogger(__name__)
SERVICE_ADDRESS = "http://169.254.169.254"


class DataSourceExoscale(sources.DataSource):

    dsname = 'Exoscale'
    url_timeout = 10
    url_retries = 6
    url_max_wait = 60

    def __init__(self, sys_cfg, distro, paths):
        sources.DataSource.__init__(self, sys_cfg, distro, paths)
        LOG.info("Initializing the Exoscale datasource")
        self.extra_config = {}

    def get_password(self):
        """Return the VM's passwords."""
        LOG.info("Fetching password from metadata service")
        password_url = "{}:8080".format(SERVICE_ADDRESS)
        response = url_helper.read_file_or_url(
            password_url,
            ssl_details=None,
            headers={"DomU_Request": "send_my_password"},
            timeout=self.url_timeout,
            retries=self.url_retries)
        password = response.contents.decode('utf-8')
        # the password is empty or already saved
        if password in ['', 'saved_password']:
            LOG.info("Password is missing or already saved")
            return None
        LOG.info("Found the password in metadata service")
        # save the password
        url_helper.read_file_or_url(
            password_url,
            ssl_details=None,
            headers={"DomU_Request": "saved_password"},
            timeout=self.url_timeout,
            retries=self.url_retries)
        LOG.info("password saved")
        return password

    def wait_for_metadata_service(self):
        """Wait for the metadata service to be reachable."""
        LOG.info("waiting for the metadata service")
        start_time = time.time()

        metadata_url = "{}/{}/meta-data/instance-id".format(
            SERVICE_ADDRESS,
            API_VERSION)

        start_time = time.time()
        url = url_helper.wait_for_url(
            urls=[metadata_url],
            max_wait=self.url_max_wait,
            timeout=self.url_timeout,
            status_cb=LOG.critical)

        if url:
            LOG.info("metadata service ok")
            return True
        else:
            wait_time = int(time.time() - start_time)
            LOG.critical(("Giving up on waiting for the metadata from %s"
                          " after %s seconds"),
                         url,
                         wait_time)
            return False

    def _get_data(self):
        """Fetch the user data, the metadata and the VM password
        from the metadata service."""
        LOG.info("fetching data")
        if not self.wait_for_metadata_service():
            return False
        start_time = time.time()
        self.userdata_raw = ec2.get_instance_userdata(API_VERSION,
                                                      SERVICE_ADDRESS,
                                                      timeout=self.url_timeout,
                                                      retries=self.url_retries)
        self.metadata = ec2.get_instance_metadata(API_VERSION,
                                                  SERVICE_ADDRESS,
                                                  timeout=self.url_timeout,
                                                  retries=self.url_retries)
        password = self.get_password()
        if password:
            self.extra_config = {
                'ssh_pwauth': True,
                'password': password,
                'chpasswd': {
                    'expire': False,
                },
            }
        get_data_time = int(time.time() - start_time)
        LOG.info("finished fetching the metadata in %s seconds",
                 get_data_time)
        return True

    def get_config_obj(self):
        return self.extra_config

    def get_instance_id(self):
        return self.metadata['instance-id']

    @property
    def availability_zone(self):
        return self.metadata['availability-zone']


# Used to match classes to dependencies
datasources = [
    (DataSourceExoscale, (sources.DEP_FILESYSTEM, sources.DEP_NETWORK)),
]


# Return a list of data sources that match this set of dependencies
def get_datasource_list(depends):
    return sources.list_from_depends(depends, datasources)
