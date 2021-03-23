import { ethers, BigNumber } from "ethers";
import PromisePool from '@supercharge/promise-pool';
import fs from 'fs/promises';
import { createObjectCsvWriter } from 'csv-writer';
import { ObjectMap } from "csv-writer/src/lib/lang/object";
import { config } from 'dotenv';

config();

const ETH_PROVIDER = process.env.ETH_PROVIDER;
const AVA_PROVIDER = process.env.AVA_PROVIDER;

const ethProvider = new ethers.providers.JsonRpcProvider(ETH_PROVIDER);
const avaProvider = new ethers.providers.JsonRpcProvider(AVA_PROVIDER);

const ethChainId = 1;
const avaChainId = 2;

const ethBridgeAddress = "0x96B845aBE346b49135B865E5CeDD735FC448C3aD";
const avaBridgeAddress = "0x6460777cDa22AD67bBb97536FFC446D65761197E";

const ethHandler = "0xdAC7Bb7Ce4fF441A235F08408e632FA1D799A147"
const avaHandler = "0x6147F5a1a4eEa5C529e2F375Bd86f8F58F8Bc990"

const avaStartBlock = 296840;
const ethStartBlock = 11912833;

const bridgeABI = [{"inputs":[{"internalType":"uint8","name":"chainID","type":"uint8"},{"internalType":"address[]","name":"initialRelayers","type":"address[]"},{"internalType":"uint256","name":"initialRelayerThreshold","type":"uint256"},{"internalType":"uint256","name":"fee","type":"uint256"},{"internalType":"uint256","name":"expiry","type":"uint256"}],"stateMutability":"nonpayable","type":"constructor"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint8","name":"destinationChainID","type":"uint8"},{"indexed":true,"internalType":"bytes32","name":"resourceID","type":"bytes32"},{"indexed":true,"internalType":"uint64","name":"depositNonce","type":"uint64"}],"name":"Deposit","type":"event"},{"anonymous":false,"inputs":[{"indexed":false,"internalType":"address","name":"account","type":"address"}],"name":"Paused","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint8","name":"originChainID","type":"uint8"},{"indexed":true,"internalType":"uint64","name":"depositNonce","type":"uint64"},{"indexed":true,"internalType":"enum Bridge.ProposalStatus","name":"status","type":"uint8"},{"indexed":false,"internalType":"bytes32","name":"resourceID","type":"bytes32"},{"indexed":false,"internalType":"bytes32","name":"dataHash","type":"bytes32"}],"name":"ProposalEvent","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint8","name":"originChainID","type":"uint8"},{"indexed":true,"internalType":"uint64","name":"depositNonce","type":"uint64"},{"indexed":true,"internalType":"enum Bridge.ProposalStatus","name":"status","type":"uint8"},{"indexed":false,"internalType":"bytes32","name":"resourceID","type":"bytes32"}],"name":"ProposalVote","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"relayer","type":"address"}],"name":"RelayerAdded","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"relayer","type":"address"}],"name":"RelayerRemoved","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"newThreshold","type":"uint256"}],"name":"RelayerThresholdChanged","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"bytes32","name":"role","type":"bytes32"},{"indexed":true,"internalType":"address","name":"account","type":"address"},{"indexed":true,"internalType":"address","name":"sender","type":"address"}],"name":"RoleGranted","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"bytes32","name":"role","type":"bytes32"},{"indexed":true,"internalType":"address","name":"account","type":"address"},{"indexed":true,"internalType":"address","name":"sender","type":"address"}],"name":"RoleRevoked","type":"event"},{"anonymous":false,"inputs":[{"indexed":false,"internalType":"address","name":"account","type":"address"}],"name":"Unpaused","type":"event"},{"inputs":[],"name":"DEFAULT_ADMIN_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"RELAYER_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"_chainID","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint8","name":"","type":"uint8"}],"name":"_depositCounts","outputs":[{"internalType":"uint64","name":"","type":"uint64"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint64","name":"","type":"uint64"},{"internalType":"uint8","name":"","type":"uint8"}],"name":"_depositRecords","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"_expiry","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"_fee","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint72","name":"","type":"uint72"},{"internalType":"bytes32","name":"","type":"bytes32"},{"internalType":"address","name":"","type":"address"}],"name":"_hasVotedOnProposal","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint72","name":"","type":"uint72"},{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"_proposals","outputs":[{"internalType":"bytes32","name":"_resourceID","type":"bytes32"},{"internalType":"bytes32","name":"_dataHash","type":"bytes32"},{"internalType":"enum Bridge.ProposalStatus","name":"_status","type":"uint8"},{"internalType":"uint256","name":"_proposedBlock","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"_relayerThreshold","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"_resourceIDToHandlerAddress","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"_totalProposals","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"_totalRelayers","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"relayerAddress","type":"address"}],"name":"adminAddRelayer","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"newFee","type":"uint256"}],"name":"adminChangeFee","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"newThreshold","type":"uint256"}],"name":"adminChangeRelayerThreshold","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"adminPauseTransfers","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"relayerAddress","type":"address"}],"name":"adminRemoveRelayer","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"handlerAddress","type":"address"},{"internalType":"address","name":"tokenAddress","type":"address"}],"name":"adminSetBurnable","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"handlerAddress","type":"address"},{"internalType":"bytes32","name":"resourceID","type":"bytes32"},{"internalType":"address","name":"contractAddress","type":"address"},{"internalType":"bytes4","name":"depositFunctionSig","type":"bytes4"},{"internalType":"bytes4","name":"executeFunctionSig","type":"bytes4"}],"name":"adminSetGenericResource","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"handlerAddress","type":"address"},{"internalType":"bytes32","name":"resourceID","type":"bytes32"},{"internalType":"address","name":"tokenAddress","type":"address"}],"name":"adminSetResource","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"adminUnpauseTransfers","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"handlerAddress","type":"address"},{"internalType":"address","name":"tokenAddress","type":"address"},{"internalType":"address","name":"recipient","type":"address"},{"internalType":"uint256","name":"amountOrTokenID","type":"uint256"}],"name":"adminWithdraw","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint8","name":"chainID","type":"uint8"},{"internalType":"uint64","name":"depositNonce","type":"uint64"},{"internalType":"bytes32","name":"dataHash","type":"bytes32"}],"name":"cancelProposal","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint8","name":"destinationChainID","type":"uint8"},{"internalType":"bytes32","name":"resourceID","type":"bytes32"},{"internalType":"bytes","name":"data","type":"bytes"}],"name":"deposit","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"uint8","name":"chainID","type":"uint8"},{"internalType":"uint64","name":"depositNonce","type":"uint64"},{"internalType":"bytes","name":"data","type":"bytes"},{"internalType":"bytes32","name":"resourceID","type":"bytes32"}],"name":"executeProposal","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint8","name":"originChainID","type":"uint8"},{"internalType":"uint64","name":"depositNonce","type":"uint64"},{"internalType":"bytes32","name":"dataHash","type":"bytes32"}],"name":"getProposal","outputs":[{"components":[{"internalType":"bytes32","name":"_resourceID","type":"bytes32"},{"internalType":"bytes32","name":"_dataHash","type":"bytes32"},{"internalType":"address[]","name":"_yesVotes","type":"address[]"},{"internalType":"address[]","name":"_noVotes","type":"address[]"},{"internalType":"enum Bridge.ProposalStatus","name":"_status","type":"uint8"},{"internalType":"uint256","name":"_proposedBlock","type":"uint256"}],"internalType":"struct Bridge.Proposal","name":"","type":"tuple"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"}],"name":"getRoleAdmin","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"uint256","name":"index","type":"uint256"}],"name":"getRoleMember","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"}],"name":"getRoleMemberCount","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"grantRole","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"hasRole","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"relayer","type":"address"}],"name":"isRelayer","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"paused","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"newAdmin","type":"address"}],"name":"renounceAdmin","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"renounceRole","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"revokeRole","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address payable[]","name":"addrs","type":"address[]"},{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"name":"transferFunds","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint8","name":"chainID","type":"uint8"},{"internalType":"uint64","name":"depositNonce","type":"uint64"},{"internalType":"bytes32","name":"resourceID","type":"bytes32"},{"internalType":"bytes32","name":"dataHash","type":"bytes32"}],"name":"voteProposal","outputs":[],"stateMutability":"nonpayable","type":"function"}];

const ethBridge = new ethers.Contract(ethBridgeAddress, bridgeABI, ethProvider);
const avaBridge = new ethers.Contract(avaBridgeAddress, bridgeABI, avaProvider);

async function findFailedProposals(originName: string, destinationName: string, 
                                   originBridge: ethers.Contract, destinationBridge: ethers.Contract, 
                                   originChangeID: number, destinationChainID: number, 
                                   destinationHandler: string, startOriginBlock: number = 0) {
    const totalDeposits = Number((await originBridge._depositCounts(destinationChainID)).toString());
    console.log("Searching thru " + totalDeposits + " deposits for")
    let noinces = [...Array(totalDeposits).keys()];

    const { results, errors } = await PromisePool
        .withConcurrency(4)
        .for(noinces)
        .process(async noince => {
            const originBridgeAddress = await originBridge.resolvedAddress
            console.log("[" + originName + " -> " + destinationName + " | Noince " + noince + "] Grabbing deposit record for " + noince);
            const records = (await originBridge._depositRecords(noince, destinationChainID));
            const hash = ethers.utils.solidityKeccak256(["address", "bytes"], [destinationHandler, records]);
            console.log("[" + originName + " -> " + destinationName + " | Noince " + noince + "] Grabbing proposal with hash " + hash)
            const proposal = await destinationBridge.getProposal(originChangeID, noince, hash);
            
            if (proposal._resourceID == "0x0000000000000000000000000000000000000000000000000000000000000000") {
                console.log("[" + originName + " -> " + destinationName + " | Noince " + noince + "] No proposal found, skipping")
                return null;
            }

            if (proposal._status == 3) {
                console.log("[" + originName + " -> " + destinationName + " | Noince " + noince + "] Proposal status success, skipping");
                return null;
            }

            console.log("[" + originName + " -> " + destinationName + " | Noince " + noince + "] Grabbing Despot event")
            const event = originBridge.filters.Deposit(null, null, noince);
            const originEvents = await originBridge.queryFilter(event, 0, 'latest')

            let originBlockNumber = "0"
            if (originEvents.length == 0) {
                originBlockNumber = "Deposit not found on Origin Chain";
                console.log("[" + originName + " -> " + destinationName + " | Noince " + noince + "] No Deposit event found")
            } else if (originEvents.length > 1) {
                originBlockNumber = "Multiple Deposit events with the noince " + noince + " found on the Origin Chain"; 
                console.log("[" + originName + " -> " + destinationName + " | Noince " + noince + "] Multiple Deposit events found with same noince")
            } else {
                const originEvent = originEvents[0];
                if (originEvent.args != null) {
                    if (originEvent.args.resourceID != proposal._resourceID) {
                        originBlockNumber = "Resource ID of Deposit event doesn't match Proposal, expected " + proposal._resourceID + " but got " + originEvent.args.resourceID;
                        console.log("[" + originName + " -> " + destinationName + " | Noince " + noince + "] Deposit event found, but proposal resource ID mismatch")
                    } else if (originEvent.args.destinationChainID != destinationChainID) {
                        originBlockNumber = "destinationChainID in Deposit event doesn't match expected " + destinationChainID + " got " + originEvent.args.destinationChainID;
                        console.log("[" + originName + " -> " + destinationName + " | Noince " + noince + "] Deposit event found, but destinationChainID  mismtach")
                    } else {
                        originBlockNumber = originEvent.blockNumber.toString();
                        console.log("[" + originName + " -> " + destinationName + " | Noince " + noince + "] Despot event found and verified")
                    }
                } else {
                    originBlockNumber = originEvent.blockNumber.toString() + " (unverified)";
                    console.log("[" + originName + " -> " + destinationName + " | Noince " + noince + "] Despot event found, but unverified (no data in event)")
                }

                if (originEvent.blockNumber < startOriginBlock) {
                    console.log("[" + originName + " -> " + destinationName + " | Noince " + noince + "] Deposit event occured before " + startOriginBlock + ", skipping");
                    return null;
                }
            }
            
            if (proposal._status != 3) {
                console.log("[" + originName + " -> " + destinationName + " | Noince " + noince + "] Proposal status is not success, logging data found")
                const yes_votes_string = proposal._yesVotes.join()
                const no_votes_string = proposal._noVotes.join()

                return {
                    'origin': originName,
                    'destination': destinationName,
                    'proposal_resource_id': proposal._resourceID,
                    'proposal_dataHash': proposal._dataHash,
                    'proposal_yes_votes_count': proposal._yesVotes.length,
                    'proposal_no_votes_count': proposal._noVotes.length,
                    'proposal_yes_votes': yes_votes_string,
                    'proposal_no_votes': no_votes_string,
                    'proposal_status': proposal._status,
                    'proposal_proposed_block': proposal._proposedBlock.toString(),
                    'origin_block_number': originBlockNumber,
                }
            }

            return null;
        })
    
    return results.filter(p => p != null);
}

async function main() {
    try {
        const tempResults = await Promise.all([
            findFailedProposals('Ethereum', 'Avalanche', ethBridge, avaBridge, ethChainId, avaChainId, avaHandler),
            findFailedProposals('Avalanche', 'Ethereum', avaBridge, ethBridge, avaChainId, ethChainId, ethHandler)
        ]);
        console.log("Collecting all data");

        const results = tempResults[0].concat(tempResults[1]) as ObjectMap<any>[];

        console.log("Creating JSON data")
        const json = JSON.stringify(results);

        console.log("Creating CSV data");
        const csvWriter = createObjectCsvWriter({
            path: 'results.csv',
            header: [
                {id: 'origin', title: 'Origin'},
                {id: 'destination', title: 'Destination'},
                {id: 'proposal_resource_id', title: 'Resource ID'},
                {id: 'proposal_dataHash', title: 'Data Hash'},
                {id: 'proposal_yes_votes_count', title: 'Yes Vote Count'},
                {id: 'proposal_no_votes_count', title: 'No Vote Count'},
                {id: 'proposal_yes_votes', title: 'Yes Votes'},
                {id: 'proposal_no_votes', title: 'No Votes'},
                {id: 'proposal_status', title: 'Status'},
                {id: 'proposal_proposed_block', title: 'Proposed Block'},
                {id: 'origin_block_number', title: 'Deposit Block Number'}
            ]
        });

        console.log("Writing JSON file");
        await fs.writeFile('results.json', json);

        console.log("Writing CSV file");
        await csvWriter.writeRecords(results);
    } catch (e) {
        console.log("Got unhandled error: " + e);
        console.log(e);
    }
}

main();
