from mocasin.common.platform import Platform, Processor, CommunicationResource, CommunicationResourceType, FrequencyDomain
from mocasin.platforms.platformDesigner import PlatformDesigner, cluster, genericProcessor
from mocasin.platforms.topologies import meshTopology, fullyConnectedTopology
from hydra.utils import instantiate

# TO-DO: check the actual latency, throughput of the eSP hardware and update the numbers
# L2 is connected to NoC and directly to LLC

class DesignerPlatformESP(Platform):
    def __init__(
        self,
        processor_cpu,
        processor_accel,
        num_cpu=4,
        num_accel=2,
        name="esp",
        symmetries_json=None,
        embedding_json=None,
    ):
        super(DesignerPlatformESP, self).__init__(
            name, symmetries_json, embedding_json
        )

        if not isinstance(processor_cpu, genericProcessor):
            processor_cpu = instantiate(processor_cpu)
        if not isinstance(processor_accel, genericProcessor):
            processor_accel = instantiate(processor_accel)

        designer = PlatformDesigner(self)
        designer.setSchedulingPolicy("FIFO", 1000)
        platform = cluster("esp", designer)

        # Router parameters for NoC
        router_params = (100, 150, 100, 60, 6000000.0)  # readLatency, writeLatency, readThroughput, writeThroughput, freq
        fd = FrequencyDomain("fd_noc", 6000000.0)
        pl = CommunicationResource(
            "noc_link",
            fd,
            CommunicationResourceType.PhysicalLink,
            100, 150, 100, 60 # readLatency, writeLatency, readThroughput, writeThroughput
        )

        l2_caches = []

        # Build CPU cluster with L1/L2
        cpu_cluster = cluster("cpu", designer)
        cpu_routers = []
        for i in range(num_cpu):
            pe = cpu_cluster.addPeToCluster(
                f"cpu_{i}",
                processor_cpu.type,
                processor_cpu.frequency_domain,
                processor_cpu.power_model,
                processor_cpu.context_load_cycles,
                processor_cpu.context_store_cycles,
            )
            l1 = cpu_cluster.addStorage(
                f"l1_cpu_{i}",
                readLatency=5,
                writeLatency=5,
                readThroughput=float("inf"),
                writeThroughput=float("inf"),
                frequency=processor_cpu.frequency_domain.frequency,
            )

            designer.connectComponents(pe, l1)
            designer.generatePrimitivesForStorage(l1)

            l2 = cpu_cluster.addStorage(
                f"l2_cpu_{i}",
                readLatency=100,
                writeLatency=100,
                readThroughput=float("inf"),
                writeThroughput=float("inf"),
                frequency=processor_cpu.frequency_domain.frequency,
            )
            router = cpu_cluster.addRouter(f"router_cpu_{i}", *router_params)

            designer.connectComponents(l1, l2)

            designer.generatePrimitivesForStorage(l2)
            designer.connectComponents(l2, router)
            cpu_routers.append(router)

            l2_caches.append(l2)

        # Build accelerator cluster
        accel_cluster = cluster("cgra", designer)
        accel_routers = []
        accels = []

        for i in range(num_accel):
            pe = accel_cluster.addPeToCluster(
                f"accel_{i}",
                processor_accel.type,
                processor_accel.frequency_domain,
                processor_accel.power_model,
                processor_accel.context_load_cycles,
                processor_accel.context_store_cycles,
            )
            accels.append(pe)
            router = accel_cluster.addRouter(f"router_accel_{i}", *router_params)
            designer.connectComponents(pe, router)
            accel_routers.append(router)

        # Shared LLC
        llc = platform.addStorage(
            "LLC",
            readLatency=200,
            writeLatency=200,
            readThroughput=float("inf"),
            writeThroughput=float("inf"),
            frequency=600000000.0,
        )

        for l2 in l2_caches:
            designer.connectComponents(l2, llc)

        for accel in accels:
            designer.connectComponents(accel, llc)

        designer.generatePrimitivesForStorage(llc)

        # RAM
        ram = platform.addStorage(
            "RAM",
            readLatency=1000,
            writeLatency=1000,
            readThroughput=float("inf"),
            writeThroughput=float("inf"),
            frequency=6000000.0,
        )
        designer.connectComponents(llc, ram)

        designer.generatePrimitivesForStorage(ram)

        # Connect all routers via NoC
        all_routers = cpu_routers + accel_routers

        noc = designer.createNetwork(
            "esp_noc",
            all_routers,
            fullyConnectedTopology,  # TO-DO: or meshTopology?
            pl
        )
        designer.generatePrimitivesForNoc(noc)
